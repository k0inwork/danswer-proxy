"""
Workspace project synchronization manager with async callbacks and blocking file uploads.
"""

import concurrent.futures
import hashlib
import json
import os
import threading
from typing import Any, Dict, List, Optional

from orchestrator.config import get_run_logger, logger
from orchestrator.models import Descriptor, DescriptorStatus


class WorkspaceProjectSync:
    IGNORE_DIRS = {'.git', 'node_modules', '__pycache__', '.venv', 'venv', '.cache', 'dist', 'build', '.idea', '.vscode', 'log', 'logs'}
    IGNORE_EXTS = ('.pyc', '.pyo', '.pyd', '.so', '.dll', '.dylib', '.tar', '.gz', '.zip', '.png', '.jpg', '.jpeg', '.gif', '.ico', '.pdf', '.log', '.tmp')
    IGNORE_FILES = {'persona_matrix_cache.json', 'workspace_sync_cache.json'}

    def __init__(self, workspace_root: str, client: Any):
        self.root = os.path.abspath(workspace_root)
        self.client = client

        path_hash = hashlib.md5(self.root.encode("utf-8")).hexdigest()
        self.project_name = f"workspace-{path_hash}"
        self.cache_file = os.path.join(self.root, "workspace_sync_cache.json")

        self.project_id: Optional[str] = None
        # Registry of all tracked descriptors indexed by canonical_name
        self.descriptors: Dict[str, Descriptor] = {}

        self.file_hashes: Dict[str, str] = {}           # path -> sha256
        self.revisions: Dict[str, int] = {}             # path -> revision int
        self.watched_files: Dict[str, str] = {}         # canonical_name -> path

        self._watcher_thread: Optional[threading.Thread] = None
        self._stop_watcher = threading.Event()
        self._lock = threading.Lock()
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="onyx_sync")

    # ------------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------------

    def _on_upload_complete(self, canonical: str, file_id: str, file_type: str) -> None:
        """Callback 1: Triggered strictly when Onyx returns valid file_id from upload_project_file."""
        with self._lock:
            desc = self.descriptors.get(canonical)
            if not desc:
                return
            desc.file_id = file_id
            desc.file_type = file_type
            desc.status = DescriptorStatus.UPLOADED
            logger.info("CALLBACK [UPLOADED]: '%s' assigned ID=%s", canonical, file_id)

        get_run_logger().log_file_upload(
            file_path=desc.file_path,
            canonical_name=canonical,
            file_id=file_id,
            project_id=desc.project_id,
            status="UPLOADED",
        )

        # Trigger second stage immediately upon upload completion
        if desc.project_id:
            try:
                self.executor.submit(self._async_attach_task, canonical, desc.project_id, file_id)
            except Exception as exc:
                logger.warning("Could not submit async attach task for '%s': %s", canonical, exc)

    def _on_attach_complete(self, canonical: str) -> None:
        """Callback 2: Triggered strictly when project-association API call succeeds."""
        with self._lock:
            desc = self.descriptors.get(canonical)
            if not desc:
                return
            desc.status = DescriptorStatus.READY
            if desc.project_id:
                try:
                    p_files = self.client.get_project_files(desc.project_id)
                    p_fids = [str(f.get("file_id") or f.get("id") or "") for f in p_files if isinstance(f, dict)] + [str(f.get("id") or f.get("file_id") or "") for f in p_files if isinstance(f, dict)]
                    logger.info("CALLBACK [READY]: '%s' successfully attached to project_id=%s (Project file count: %d, contains file_id=%s: %s)", canonical, desc.project_id, len(p_files), desc.file_id, desc.file_id in p_fids)
                except Exception as p_err:
                    logger.info("CALLBACK [READY]: '%s' successfully attached to project_id=%s (Verification lookup error: %s)", canonical, desc.project_id, p_err)
            else:
                logger.info("CALLBACK [READY]: '%s' successfully attached to project_id=%s", canonical, desc.project_id)
            self.save_cache()

        get_run_logger().log_file_upload(
            file_path=desc.file_path,
            canonical_name=canonical,
            file_id=desc.file_id,
            project_id=desc.project_id,
            status="READY",
        )

    def _on_sync_failure(self, canonical: str, stage: str, error: Exception) -> None:
        """Callback Error Handler."""
        with self._lock:
            desc = self.descriptors.get(canonical)
            if desc:
                desc.status = DescriptorStatus.FAILED
                desc.error_message = f"{stage} failed: {error}"
            logger.error("CALLBACK [FAILED]: '%s' at stage '%s': %s", canonical, stage, error)

        get_run_logger().log_file_upload(
            file_path=desc.file_path if desc else "",
            canonical_name=canonical,
            status="FAILED",
            error=f"{stage} failed: {error}",
        )

    # ------------------------------------------------------------------------
    # Async Task Pipeline
    # ------------------------------------------------------------------------

    def _async_upload_task(self, canonical: str, file_path: str, payload_bytes: bytes) -> None:
        try:
            with self._lock:
                desc = self.descriptors.get(canonical)

            existing_file_id = getattr(desc, 'file_id', None)
            project_id = getattr(desc, 'project_id', None) or self.project_id

            if existing_file_id and project_id:
                try:
                    self.client.delete_project_file(existing_file_id, project_id)
                except Exception as del_err:
                    logger.debug("Non-fatal error during pre-upload deletion of file_id=%s: %s", existing_file_id, del_err)

            res = self.client.upload_project_file(
                project_id=self.project_id or "",
                filename=canonical,
                content_bytes=payload_bytes,
            )

            fid = str(res.get("file_id") or res.get("id") or "")
            ftype = res.get("file_type", "plain_text")

            if fid and hasattr(self.client, "wait_for_file_processing"):
                self.client.wait_for_file_processing(fid)

            # Fire Uploaded Callback
            self._on_upload_complete(canonical, fid, ftype)
        except Exception as exc:
            self._on_sync_failure(canonical, "UPLOAD", exc)

    def _async_attach_task(self, canonical: str, project_id: str, file_id: str) -> None:
        try:
            # Note: upload_project_file links project_id during upload.
            # If attach_file_to_project returns a secondary file mapping or success, mark READY without replacing file_id if redundant.
            self._on_attach_complete(canonical)
        except Exception as exc:
            self._on_sync_failure(canonical, "ATTACH", exc)

    # ------------------------------------------------------------------------
    # Pipeline Dispatcher
    # ------------------------------------------------------------------------

    def dispatch_file_sync(self, canonical: str, file_path: str, payload_bytes: bytes) -> Descriptor:
        with self._lock:
            desc = self.descriptors.get(canonical)
            if desc:
                desc.file_path = file_path
                desc.status = DescriptorStatus.PENDING_UPLOAD
                desc.error_message = None
            else:
                desc = Descriptor(
                    canonical_name=canonical,
                    file_path=file_path,
                    status=DescriptorStatus.PENDING_UPLOAD,
                    project_id=self.project_id,
                )
                self.descriptors[canonical] = desc

        # Non-blocking async dispatch
        self.executor.submit(self._async_upload_task, canonical, file_path, payload_bytes)
        return desc

    def upload_and_attach_blocking(
        self,
        file_path: str,
        content: Optional[str] = None,
        timeout: float = 10.0,
    ) -> Optional[Descriptor]:
        """
        Synchronously uploads, waits for processing, and attaches a workspace file to the active Onyx project.
        Blocks the calling thread until DescriptorStatus is READY or FAILED.
        """
        is_dir_canonical = file_path.startswith("TOP_FOLDER_") or file_path.startswith("FOLDER_")
        canonical = file_path if is_dir_canonical else self.canonical_name(file_path, is_dir=False)

        # 1. Resolve content from memory or disk
        if content is None:
            disk_path = os.path.join(self.root, file_path) if not os.path.isabs(file_path) else file_path
            if os.path.exists(disk_path):
                try:
                    with open(disk_path, "r", encoding="utf-8", errors="replace") as f:
                        content = f.read()
                except Exception as read_err:
                    logger.warning("Failed to read file from disk %s: %s", disk_path, read_err)
                    return None
            else:
                logger.warning("File not found on workspace disk for blocking sync: %s", disk_path)
                return None

        if is_dir_canonical:
            full_payload = content.encode("utf-8") if isinstance(content, str) else content
            content_str = content if isinstance(content, str) else content.decode("utf-8", errors="replace")
            body_str = content_str.split("\n\n", 1)[1] if "\n\n" in content_str else content_str
            content_hash = hashlib.sha256(body_str.encode("utf-8")).hexdigest()
        else:
            content_bytes = content.encode("utf-8") if isinstance(content, str) else content
            content_hash = hashlib.sha256(content_bytes).hexdigest()
            abs_path = os.path.abspath(file_path if os.path.isabs(file_path) else os.path.join(self.root, file_path))
            rev = self.revisions.get(canonical, 0) + 1
            header = (
                f"# WORKSPACE FILE SYNC: {abs_path}\n"
                f"# SHA256: {content_hash[:12]} | REVISION: {rev}\n"
                f"# ====================================================\n\n"
            )
            full_payload = header.encode("utf-8") + content_bytes
            self.revisions[canonical] = rev
            self.watched_files[canonical] = abs_path

        self.file_hashes[canonical] = content_hash

        with self._lock:
            desc = self.descriptors.get(canonical)
            if not desc:
                desc = Descriptor(
                    canonical_name=canonical,
                    file_path=file_path,
                    status=DescriptorStatus.PENDING_UPLOAD,
                    project_id=self.project_id,
                )
                self.descriptors[canonical] = desc
            else:
                desc.status = DescriptorStatus.PENDING_UPLOAD
                desc.file_path = file_path

        try:
            # Check and cleanup existing file if present
            existing_fid = getattr(desc, 'file_id', None)
            if existing_fid and self.project_id:
                try:
                    self.client.delete_project_file(existing_fid, self.project_id)
                except Exception:
                    pass

            # 2. Direct upload
            res = self.client.upload_project_file(
                project_id=self.project_id or "",
                filename=canonical,
                content_bytes=full_payload,
            )
            fid = str(res.get("file_id") or res.get("id") or "")
            ftype = res.get("file_type", "plain_text")

            # 3. Wait for file processing
            if fid and hasattr(self.client, "wait_for_file_processing"):
                self.client.wait_for_file_processing(fid)

            # Update descriptor state directly without launching async attach task
            with self._lock:
                desc.file_id = fid
                desc.file_type = ftype
                desc.status = DescriptorStatus.UPLOADED

            get_run_logger().log_file_upload(
                file_path=desc.file_path,
                canonical_name=canonical,
                file_id=fid,
                project_id=desc.project_id,
                status="UPLOADED",
            )

            # 4. Direct attach - mark READY directly since upload_project_file links project_id during POST upload
            self._on_attach_complete(canonical)

            with self._lock:
                return self.descriptors.get(canonical)
        except Exception as exc:
            self._on_sync_failure(canonical, "BLOCKING_SYNC", exc)
            return None

    def write_workspace_file(self, file_path: str, content: str) -> Optional[Descriptor]:
        """
        Writes content to a file in the workspace directory (self.root), creates parent directories
        if necessary, and syncs/attaches the updated file synchronously with Onyx using blocking upload.
        """
        target_path = os.path.join(self.root, file_path) if not os.path.isabs(file_path) else file_path
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            f.write(content)
        get_run_logger().log_action(
            category="DISK_WRITE",
            action="WRITE_WORKSPACE_FILE",
            details={"file_path": target_path, "bytes": len(content.encode("utf-8"))},
        )
        return self.upload_and_attach_blocking(file_path=target_path, content=content)

    def execute_local_non_read_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
        """
        Executes a local tool against the workspace disk (e.g. list_dir, grep_search, find_files, write_file).
        """
        t_name = (tool_name or "").lower().strip()
        res_output = ""

        # 1. Directory listing (list_dir, ls, dir)
        if t_name in {"list_dir", "ls", "dir"}:
            req_path = args.get("path") or args.get("directory") or args.get("dir_path") or "."
            target_dir = os.path.join(self.root, req_path) if not os.path.isabs(req_path) else req_path
            if os.path.exists(target_dir) and os.path.isdir(target_dir):
                try:
                    entries = sorted(os.listdir(target_dir))
                    formatted_entries = []
                    for e in entries:
                        full_e = os.path.join(target_dir, e)
                        suffix = "/" if os.path.isdir(full_e) else ""
                        formatted_entries.append(f"{e}{suffix}")
                    res_output = f"Directory listing of '{req_path}':\n" + "\n".join(formatted_entries[:100])
                except Exception as err:
                    res_output = f"Error listing directory '{req_path}': {err}"
            else:
                res_output = f"Directory not found: '{req_path}'"

        # 2. Grep search (grep_search, grep, search_code)
        elif t_name in {"grep_search", "grep", "search_code"}:
            query = args.get("query") or args.get("pattern") or args.get("regex") or ""
            search_path = args.get("path") or "."
            target_dir = os.path.join(self.root, search_path) if not os.path.isabs(search_path) else search_path
            matches = []
            if os.path.exists(target_dir):
                for root_dir, _, files in os.walk(target_dir):
                    for file in files:
                        if file.startswith(".") or file.endswith((".pyc", ".png", ".jpg", ".cache")):
                            continue
                        fpath = os.path.join(root_dir, file)
                        try:
                            with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                                for line_no, line in enumerate(f, 1):
                                    if query and query in line:
                                        rel = os.path.relpath(fpath, self.root)
                                        matches.append(f"{rel}:{line_no}: {line.strip()}")
                                        if len(matches) >= 30:
                                            break
                        except Exception:
                            continue
                        if len(matches) >= 30:
                            break
                    if len(matches) >= 30:
                        break
            if matches:
                res_output = f"Found {len(matches)} matches for '{query}':\n" + "\n".join(matches)
            else:
                res_output = f"No matches found for '{query}' in path '{search_path}'."

        # 3. Find files / glob (find_files, glob, find)
        elif t_name in {"find_files", "glob", "find"}:
            search_pattern = args.get("pattern") or args.get("query") or "*"
            search_path = args.get("path") or "."
            target_dir = os.path.join(self.root, search_path) if not os.path.isabs(search_path) else search_path
            matches = []
            if os.path.exists(target_dir):
                for root_dir, _, files in os.walk(target_dir):
                    for file in files:
                        if file.startswith("."):
                            continue
                        rel_f = os.path.relpath(os.path.join(root_dir, file), self.root)
                        if search_pattern == "*" or search_pattern.lower() in file.lower():
                            matches.append(rel_f)
                            if len(matches) >= 50:
                                break
                    if len(matches) >= 50:
                        break
            if matches:
                res_output = f"Found {len(matches)} matching files for '{search_pattern}':\n" + "\n".join(matches)
            else:
                res_output = f"No files matching '{search_pattern}' found in path '{search_path}'."

        # 4. Write / Create / Edit file operations (write_file, write, create_file, edit_file, modify_file, save_file, replace_in_file)
        elif t_name in {"write_file", "write", "create_file", "edit_file", "modify_file", "save_file", "replace_in_file"}:
            req_path = args.get("file_path") or args.get("path") or args.get("filename") or args.get("target_file")
            if not req_path:
                res_output = "Error: File path argument missing for write operation."
            else:
                content = args.get("content") or args.get("text") or args.get("file_content") or args.get("code") or ""

                # Check if replace_in_file style string replacement is requested
                old_str = args.get("old_str") or args.get("search") or args.get("find")
                new_str = args.get("new_str") or args.get("replace")
                if old_str is not None and new_str is not None:
                    target_path = os.path.join(self.root, req_path) if not os.path.isabs(req_path) else req_path
                    if os.path.exists(target_path):
                        try:
                            with open(target_path, "r", encoding="utf-8", errors="ignore") as f:
                                existing_content = f.read()
                            if old_str in existing_content:
                                content = existing_content.replace(old_str, new_str)
                            else:
                                res_output = f"String '{old_str}' not found in file '{req_path}'."
                        except Exception as err:
                            res_output = f"Error reading file '{req_path}' for replacement: {err}"

                if not res_output:
                    try:
                        desc = self.write_workspace_file(req_path, content)
                        res_output = f"Successfully wrote {len(content.encode('utf-8'))} bytes to file '{req_path}' in workspace."
                    except Exception as err:
                        res_output = f"Error writing file '{req_path}': {err}"

        else:
            res_output = f"Tool '{tool_name}' executed with arguments: {json.dumps(args, ensure_ascii=False)}"

        get_run_logger().log_tool_call(
            tool_name=tool_name,
            arguments=args,
            result_summary=res_output,
            intercepted=False,
        )
        return res_output

    # ------------------------------------------------------------------------
    # Descriptor Accessors & Utilities
    # ------------------------------------------------------------------------

    def get_ready_descriptors(self) -> List[Dict[str, Any]]:
        """Returns only file descriptors that have reached READY state via on_attach_complete callback."""
        with self._lock:
            ready_list = []
            for desc in self.descriptors.values():
                if desc.status == DescriptorStatus.READY and desc.file_id:
                    ready_list.append(desc.to_onyx_dict())
            return ready_list

    def save_cache(self) -> None:
        try:
            cache = {
                "file_hashes": self.file_hashes,
                "revisions": self.revisions
            }
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Failed to save workspace sync cache: %s", e)

    def sanitize_path(self, path: str) -> str:
        abs_p = os.path.abspath(os.path.join(self.root, path)) if not os.path.isabs(path) else os.path.abspath(path)
        if abs_p == self.root:
            folder_name = os.path.basename(self.root) or "root"
            clean = folder_name.replace("/", "_").replace("\\", "_").replace(".", "_").strip("_")
            return clean or "root"
        rel = os.path.relpath(abs_p, self.root) if abs_p.startswith(self.root) else abs_p
        clean = rel.replace("/", "_").replace("\\", "_").replace(".", "_").strip("_")
        return clean or "root"

    def canonical_name(self, path: str, is_dir: bool = False) -> str:
        clean = self.sanitize_path(path)
        prefix = "FOLDER" if is_dir else "FILE"
        return f"{prefix}_{clean}.txt"

    def initialize_project(self) -> None:
        try:
            logger.info("Initializing per-directory Onyx project: '%s' for path '%s'", self.project_name, self.root)

            if os.path.exists(self.cache_file):
                try:
                    with open(self.cache_file, "r", encoding="utf-8") as f:
                        cache = json.load(f)
                    self.file_hashes = cache.get("file_hashes", {})
                    self.revisions = cache.get("revisions", {})
                    self.file_hashes = {str(k): str(v) for k, v in self.file_hashes.items()}
                    self.revisions = {str(k): int(v) for k, v in self.revisions.items()}
                    logger.info("Loaded workspace sync cache from %s", self.cache_file)
                except Exception as e:
                    logger.warning("Failed to load workspace sync cache: %s", e)

            projects = self.client.get_user_projects()
            match = next(
                (p for p in projects if isinstance(p, dict) and (
                    p.get("name") == self.project_name or
                    p.get("title") == self.project_name or
                    str(p.get("name", "")).strip().lower() == self.project_name.lower()
                )),
                None
            )

            if match:
                self.project_id = str(match.get("id"))
                logger.info("Found existing Onyx project_id=%s for name=%s", self.project_id, self.project_name)
                for f in match.get("files", []):
                    if isinstance(f, dict) and f.get("name"):
                        cname = f["name"]
                        fid = str(f.get("file_id") or f.get("id") or "")
                        ftype = f.get("type") or "plain_text"
                        self.descriptors[cname] = Descriptor(
                            canonical_name=cname,
                            file_path="",
                            file_id=fid,
                            file_type=ftype,
                            status=DescriptorStatus.READY,
                            project_id=self.project_id
                        )
            else:
                new_proj = self.client.create_project(
                    name=self.project_name,
                    description=f"Automated workspace file context for path {self.root}"
                )
                self.project_id = str(new_proj.get("id"))
                logger.info("Created new Onyx project_id=%s for name=%s", self.project_id, self.project_name)

            if self.project_id:
                p_files = self.client.get_project_files(self.project_id)
                file_groups: Dict[str, List[Dict[str, Any]]] = {}
                for f in p_files:
                    if isinstance(f, dict) and f.get("name"):
                        cname = f["name"]
                        file_groups.setdefault(cname, []).append(f)

                for cname, flist in file_groups.items():
                    keep_f = flist[-1]
                    fid = str(keep_f.get("file_id") or keep_f.get("id") or "")
                    ftype = keep_f.get("type") or "plain_text"

                    if len(flist) > 1:
                        for dup_f in flist[:-1]:
                            dup_fid = str(dup_f.get("file_id") or dup_f.get("id") or "")
                            if dup_fid and dup_fid != fid:
                                logger.info("Cleaning up duplicate project file '%s' (file_id=%s)", cname, dup_fid)
                                try:
                                    self.client.delete_project_file(dup_fid, self.project_id)
                                except Exception as del_err:
                                    logger.warning("Failed deleting duplicate file %s: %s", dup_fid, del_err)

                    if fid and self.project_id:
                        self.descriptors[cname] = Descriptor(
                            canonical_name=cname,
                            file_path="",
                            file_id=fid,
                            file_type=ftype,
                            status=DescriptorStatus.READY,
                            project_id=self.project_id
                        )
                        logger.info("Registered active project file descriptor '%s' (file_id=%s)", cname, fid)

            top_folder_cname = "TOP_FOLDER_" + self.sanitize_path(self.root) + ".txt"
            top_desc = self.descriptors.get(top_folder_cname)
            if not top_desc or top_desc.status != DescriptorStatus.READY:
                if top_folder_cname in self.file_hashes:
                    del self.file_hashes[top_folder_cname]

            self.update_top_folder()
            self.sync_root_files()
            self.start_background_watcher()
        except Exception as exc:
            logger.warning("Could not complete project initialization: %s", exc)

    def sync_root_files(self) -> None:
        if not os.path.isdir(self.root):
            return
        try:
            for dirpath, dirnames, filenames in os.walk(self.root):
                dirnames[:] = [d for d in dirnames if d not in self.IGNORE_DIRS and not d.startswith('.')]

                for fname in filenames:
                    if fname.startswith('.') or fname.endswith(self.IGNORE_EXTS) or fname in self.IGNORE_FILES:
                        continue
                    full_path = os.path.join(dirpath, fname)
                    if os.path.isfile(full_path):
                        if os.path.getsize(full_path) > 2 * 1024 * 1024:
                            continue

                        canonical = self.canonical_name(full_path, is_dir=False)
                        if canonical in self.descriptors and self.descriptors[canonical].status == DescriptorStatus.READY:
                            try:
                                with open(full_path, 'r', encoding='utf-8', errors='ignore') as f:
                                    text = f.read()
                                self.on_tool_read(full_path, text)
                            except Exception as exc:
                                logger.debug("Could not auto-sync existing project file '%s': %s", fname, exc)
        except Exception as exc:
            logger.warning("Error syncing existing workspace files: %s", exc)

    def start_background_watcher(self, poll_interval_sec: float = 3.0) -> None:
        if self._watcher_thread and self._watcher_thread.is_alive():
            return

        self._stop_watcher.clear()
        self._watcher_thread = threading.Thread(
            target=self._background_watcher_loop,
            args=(poll_interval_sec,),
            daemon=True,
            name="WorkspaceProjectSyncWatcher"
        )
        self._watcher_thread.start()
        logger.info("Started async background file & project tree watcher thread (poll=%.1fs)", poll_interval_sec)

    def stop_background_watcher(self) -> None:
        self._stop_watcher.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=2.0)
            logger.info("Stopped async background file watcher thread.")

    def _background_watcher_loop(self, poll_interval: float) -> None:
        while not self._stop_watcher.is_set():
            try:
                self.update_top_folder()
                self.sync_root_files()
                self.check_and_refresh_watched_files()
            except Exception as exc:
                logger.debug("Error in background file watcher loop: %s", exc)

            self._stop_watcher.wait(timeout=poll_interval)

    def generate_tree_map(self) -> str:
        lines = [f"PROJECT ROOT DIRECTORY: {self.root}\n"]

        for dirpath, dirnames, filenames in os.walk(self.root, topdown=True):
            dirnames[:] = [
                d for d in dirnames
                if d not in self.IGNORE_DIRS and not d.startswith('.')
            ]

            rel_dir = os.path.relpath(dirpath, self.root)
            prefix = "" if rel_dir == "." else f"{rel_dir}/"

            for fname in sorted(filenames):
                if fname.startswith('.') or fname.endswith(self.IGNORE_EXTS) or fname in self.IGNORE_FILES:
                    continue

                full_path = os.path.join(dirpath, fname)
                lines.append(f" - {prefix}{fname}")

        return "\n".join(lines)

    def update_top_folder(self, blocking: bool = False) -> Optional[Descriptor]:
        tree_text = self.generate_tree_map()
        tree_hash = hashlib.sha256(tree_text.encode('utf-8')).hexdigest()
        canonical = f"TOP_FOLDER_{self.sanitize_path(self.root)}.txt"

        desc = self.descriptors.get(canonical)
        if not blocking and self.file_hashes.get(canonical) == tree_hash and desc and desc.status in {DescriptorStatus.PENDING_UPLOAD, DescriptorStatus.UPLOADED, DescriptorStatus.READY}:
            return desc

        if not blocking and desc and desc.status == DescriptorStatus.READY and canonical not in self.file_hashes:
            self.file_hashes[canonical] = tree_hash
            self.save_cache()
            return desc

        header = f"# TOP_FOLDER PROJECT MAP: {self.root}\n# SHA256: {tree_hash[:12]}\n# ====================================================\n\n"
        full_payload = (header + tree_text).encode('utf-8')

        self.file_hashes[canonical] = tree_hash
        get_run_logger().log_file_read(
            file_path=self.root,
            canonical_name=canonical,
            size_bytes=len(full_payload),
            source="update_top_folder",
        )
        if blocking:
            return self.upload_and_attach_blocking(file_path=canonical, content=full_payload.decode('utf-8', errors='replace'))
        return self.dispatch_file_sync(canonical, self.root, full_payload)

    def on_tool_read(self, file_path: str, content: str) -> Optional[Descriptor]:
        abs_path = os.path.abspath(file_path if os.path.isabs(file_path) else os.path.join(self.root, file_path))
        canonical = self.canonical_name(abs_path, is_dir=False)

        content_bytes = content.encode('utf-8') if isinstance(content, str) else content
        content_hash = hashlib.sha256(content_bytes).hexdigest()

        desc = self.descriptors.get(canonical)
        if self.file_hashes.get(canonical) == content_hash and desc and desc.status in {DescriptorStatus.PENDING_UPLOAD, DescriptorStatus.UPLOADED, DescriptorStatus.READY}:
            return desc

        rev = self.revisions.get(canonical, 0) + 1
        header = (
            f"# WORKSPACE FILE SYNC: {abs_path}\n"
            f"# SHA256: {content_hash[:12]} | REVISION: {rev}\n"
            f"# ====================================================\n\n"
        )
        full_payload = header.encode('utf-8') + content_bytes

        self.file_hashes[canonical] = content_hash
        self.revisions[canonical] = rev
        self.watched_files[canonical] = abs_path

        get_run_logger().log_file_read(
            file_path=abs_path,
            canonical_name=canonical,
            size_bytes=len(content_bytes),
            revision=rev,
            source="on_tool_read",
        )

        return self.dispatch_file_sync(canonical, abs_path, full_payload)

    def on_folder_read(self, folder_path: str, listing_text: str) -> Optional[Descriptor]:
        abs_path = os.path.abspath(folder_path if os.path.isabs(folder_path) else os.path.join(self.root, folder_path))
        canonical = self.canonical_name(abs_path, is_dir=True)

        content_hash = hashlib.sha256(listing_text.encode('utf-8')).hexdigest()
        desc = self.descriptors.get(canonical)
        if self.file_hashes.get(canonical) == content_hash and desc and desc.status in {DescriptorStatus.PENDING_UPLOAD, DescriptorStatus.UPLOADED, DescriptorStatus.READY}:
            return desc

        header = f"# WORKSPACE FOLDER LISTING: {abs_path}\n# ====================================================\n\n"
        full_payload = (header + listing_text).encode('utf-8')

        self.file_hashes[canonical] = content_hash
        get_run_logger().log_file_read(
            file_path=abs_path,
            canonical_name=canonical,
            size_bytes=len(full_payload),
            source="on_folder_read",
        )
        return self.dispatch_file_sync(canonical, abs_path, full_payload)

    def check_and_refresh_watched_files(self) -> None:
        for canonical, abs_path in list(self.watched_files.items()):
            if os.path.isfile(abs_path):
                try:
                    with open(abs_path, 'r', encoding='utf-8', errors='ignore') as f:
                        text = f.read()
                    self.on_tool_read(abs_path, text)
                except Exception as exc:
                    logger.warning("Could not auto-refresh watched file '%s': %s", abs_path, exc)

    def get_system_context_header(self) -> str:
        ready_descriptors = {k: v for k, v in self.descriptors.items() if v.status == DescriptorStatus.READY}
        if not ready_descriptors:
            return ""

        top_folder_doc = next((k for k in ready_descriptors if k.startswith("TOP_FOLDER")), None)
        file_docs = [k for k in ready_descriptors if k.startswith("FILE_")]
        folder_docs = [k for k in ready_descriptors if k.startswith("FOLDER_")]

        lines = [
            "\n<workspace_context>",
            f"LOCAL WORKSPACE PATH: {self.root}",
            f"PER-DIRECTORY PROJECT: {self.project_name} (ID: {self.project_id or 'default'})",
            "The following workspace structure and inspected files are attached as project document descriptors to this session:",
        ]

        if top_folder_doc:
            lines.append(f" - Top Directory Map: `{top_folder_doc}`")
        for fdoc in file_docs:
            rev = self.revisions.get(fdoc, 1)
            lines.append(f" - Inspected File: `{fdoc}` (Rev {rev})")
        for fldoc in folder_docs:
            lines.append(f" - Inspected Subdirectory: `{fldoc}`")

        lines.extend([
            "",
            "OPERATIONAL RULES FOR MODEL:",
            "1. When asked about project structure or file locations, consult the `TOP_FOLDER_...` attached document if present.",
            "2. If a local file or subdirectory is already attached as a project document descriptor (e.g. starting with `FILE_` or `FOLDER_`), refer to and read it directly from your attached context/documents. Do NOT call local filesystem tools or make redundant read requests for files already present in your context.",
            "3. If a file or directory is NOT already attached to your context, emit the appropriate `<local_tool>` tag (e.g. `read_file`, `list_dir`, `grep_search`) immediately to inspect or read it. Do NOT refuse or state that you lack file access.",
            "4. All attached documents represent live, real-time code from the user's workspace.",
            "5. Do NOT state that you lack file access or spawn subagents to re-read files that are already attached in your descriptors.",
            "</workspace_context>\n"
        ])
        return "\n".join(lines)
