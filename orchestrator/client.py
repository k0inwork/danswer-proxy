"""
Resilient HTTP client for Onyx / Danswer API with retry adapters and SSE streams.
"""

import json
import time
from typing import Any, Dict, Iterator, List, Optional
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from orchestrator.config import (
    API_TIMEOUT,
    MODELS,
    REAL_TALK_MODEL,
    get_run_logger,
    logger,
)
from orchestrator.models import session_registry
from orchestrator.tool_parser import (
    extract_all_local_tool_invocations,
    extract_local_tool_invocation,
)


class DanswerClient:
    def __init__(self, danswer_url: str, api_token: str):
        self.danswer_url = danswer_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {api_token}",
            "Accept": "application/json",
        })

        retries = Retry(
            total=3,
            backoff_factor=1.5,
            status_forcelist=[502, 503, 504],
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @staticmethod
    def raise_for_api_error(response: requests.Response) -> None:
        try:
            response.raise_for_status()
        except Exception as exc:
            if hasattr(requests, "HTTPError") and isinstance(exc, getattr(requests, "HTTPError")):
                raise RuntimeError(
                    f"Onyx API error {getattr(response, 'status_code', 'unknown')}: {str(getattr(response, 'text', ''))[:4000]}"
                ) from exc
            elif getattr(response, "status_code", 200) >= 400:
                raise RuntimeError(
                    f"Onyx API error {getattr(response, 'status_code', 'unknown')}: {str(getattr(response, 'text', ''))[:4000]}"
                ) from exc

    def _safe_request(self, method: str, url: str, **kwargs) -> requests.Response:
        kwargs["allow_redirects"] = False
        response = self.session.request(method, url, **kwargs)
        if response.status_code in (301, 302, 307, 308):
            loc = response.headers.get("Location", "")
            if loc:
                if loc.startswith("/api/"):
                    target_url = f"{self.danswer_url}{loc}"
                    return self.session.request(method, target_url, **kwargs)
                elif loc.startswith(self.danswer_url):
                    return self.session.request(method, loc, **kwargs)
        return response

    def get_recent_files(self) -> Optional[List[Dict[str, Any]]]:
        """Fetch recently uploaded user files to check processing status and metadata."""
        try:
            response = self._safe_request("GET", f"{self.danswer_url}/api/user/files/recent", timeout=API_TIMEOUT)
            if response.status_code in (200, 201):
                data = response.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    return data.get("files") or data.get("user_files") or data.get("recent_files") or []
        except Exception as exc:
            logger.debug("Failed to fetch recent files: %s", exc)
        return None

    def get_user_file_snapshot(self, user_file_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a single UserFileSnapshot by its user-file UUID (includes processing status)."""
        try:
            response = self._safe_request(
                "GET",
                f"{self.danswer_url}/api/user/projects/file/{user_file_id}",
                timeout=API_TIMEOUT,
            )
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            logger.debug("Failed to fetch user file snapshot %s: %s", user_file_id, exc)
        return None

    @staticmethod
    def _extract_status(file_obj: Dict[str, Any]) -> str:
        status = str(file_obj.get("status") or "").upper()
        if not status:
            # Older shapes signal completion only by chunk/token counters being set
            if file_obj.get("chunk_count") is not None:
                status = "COMPLETED"
            else:
                status = "COMPLETED"
        return status

    def wait_for_file_processing(
        self,
        file_id: str,
        timeout: float = 30.0,
        poll_interval: float = 0.5,
        user_file_id: str = "",
    ) -> bool:
        """
        Polls Onyx until file processing status is COMPLETED or FAILED.
        Prefers the per-file status endpoint keyed by the user-file UUID; falls
        back to /api/user/files/recent matched on either id key.
        Returns True if processing succeeded or status cannot be determined.
        """
        if not file_id and not user_file_id:
            return True

        start_time = time.time()
        while time.time() - start_time < timeout:
            checked = False
            if user_file_id:
                snapshot = self.get_user_file_snapshot(user_file_id)
                if snapshot is not None:
                    checked = True
                    status = self._extract_status(snapshot)
                    if status == "COMPLETED":
                        logger.info("File processing completed for user_file_id=%s", user_file_id)
                        return True
                    if status == "FAILED":
                        logger.warning("File processing failed for user_file_id=%s", user_file_id)
                        return False
            if not checked:
                recent_files = self.get_recent_files()
                if recent_files:
                    for file_obj in recent_files:
                        ids = {
                            str(file_obj.get("id") or ""),
                            str(file_obj.get("file_id") or ""),
                        }
                        if str(file_id) in ids or str(user_file_id) in ids:
                            status = self._extract_status(file_obj)
                            if status == "COMPLETED":
                                logger.info("File processing completed for file_id=%s", file_id)
                                return True
                            if status == "FAILED":
                                logger.warning("File processing failed for file_id=%s", file_id)
                                return False
                            checked = True
                            break

            time.sleep(poll_interval)

        logger.warning(
            "Timed out waiting for file processing (file_id=%s user_file_id=%s); proceeding",
            file_id,
            user_file_id,
        )
        return True

    def attach_file_to_project(self, project_id: Any, file_id: str) -> bool:
        """Links an uploaded user-file (by its user-file UUID) to a project.

        Upstream endpoint: POST /api/user/projects/{project_id}/files/{file_id}
        (returns the linked UserFileSnapshot)."""
        pid_str = str(project_id).strip() if project_id is not None else ""
        fid = (file_id or "").strip()
        if not pid_str or not fid:
            return False

        endpoints = [
            (f"{self.danswer_url}/api/user/projects/{pid_str}/files/{fid}", "POST"),
        ]

        for ep, method in endpoints:
            try:
                res = self._safe_request(method, ep, timeout=API_TIMEOUT)

                logger.info("Attachment endpoint %s returned HTTP %s: %s", ep, res.status_code, res.text[:200])
                if res.status_code in (200, 201, 204):
                    get_run_logger().log_action(
                        category="FILE_ATTACH",
                        action="SUCCESS",
                        details={"project_id": pid_str, "file_id": fid, "endpoint": ep, "response_status": res.status_code},
                    )
                    return True
            except Exception as exc:
                logger.debug("Failed endpoint %s: %s", ep, exc)
                continue

        # Fallback check: Verify if fid is present in project files (by either id key)
        try:
            p_files = self.get_project_files(pid_str)
            for f in p_files:
                if isinstance(f, dict):
                    if fid in {str(f.get("id") or ""), str(f.get("file_id") or "")}:
                        return True
        except Exception:
            pass

        logger.warning("Could not attach file_id=%s to project_id=%s across candidate endpoints.", fid, pid_str)
        get_run_logger().log_action(
            category="FILE_ATTACH",
            action="FAILED",
            details={"project_id": pid_str, "file_id": fid},
        )
        return False

    def set_project_instructions(self, project_id: Any, instructions: str) -> bool:
        """Upsert system-level project instructions (inherited by all project chat sessions)."""
        pid_str = str(project_id).strip() if project_id is not None else ""
        if not pid_str:
            return False
        try:
            response = self._safe_request(
                "POST",
                f"{self.danswer_url}/api/user/projects/{pid_str}/instructions",
                json={"instructions": instructions},
                timeout=API_TIMEOUT,
            )
            if response.status_code in (200, 201, 204):
                logger.info("Project instructions updated for project_id=%s", pid_str)
                return True
            logger.warning("Failed to set project instructions for %s: HTTP %s %s", pid_str, response.status_code, response.text[:200])
        except Exception as exc:
            logger.warning("Error setting project instructions for %s: %s", pid_str, exc)
        return False

    def fetch_personas(self) -> List[Dict[str, Any]]:
        response = self.session.get(f"{self.danswer_url}/api/persona", timeout=API_TIMEOUT)
        self.raise_for_api_error(response)
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("personas", [])
        return []

    def fetch_tools(self) -> Any:
        response = self.session.get(f"{self.danswer_url}/api/tool", timeout=API_TIMEOUT)
        self.raise_for_api_error(response)
        return response.json()

    def fetch_chat_sessions(self) -> List[Dict[str, Any]]:
        response = self.session.get(
            f"{self.danswer_url}/api/chat/get-user-chat-sessions",
            timeout=API_TIMEOUT,
        )
        self.raise_for_api_error(response)
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return data.get("sessions", [])
        return []

    def get_user_projects(self) -> List[Dict[str, Any]]:
        endpoints = [
            f"{self.danswer_url}/api/user/projects",
            f"{self.danswer_url}/api/user/projects/",
        ]
        for url in endpoints:
            try:
                response = self._safe_request("GET", url, timeout=API_TIMEOUT)
                if response.status_code in (301, 302, 307, 308, 404, 405, 422):
                    continue
                self.raise_for_api_error(response)
                data = response.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    res = (
                        data.get("projects")
                        or data.get("data")
                        or data.get("user_projects")
                        or data.get("items")
                        or data.get("results")
                    )
                    if isinstance(res, list):
                        return res
            except Exception as exc:
                logger.debug("Endpoint %s failed: %s", url, exc)
                continue
        logger.warning("All user projects endpoints returned 404/redirect/405 or failed.")
        return []

    def get_project_files(self, project_id: str) -> List[Dict[str, Any]]:
        pid = (project_id or "").strip()
        if not pid:
            return []
        endpoints = [
            f"{self.danswer_url}/api/user/projects/files/{pid}",
        ]
        for url in endpoints:
            try:
                response = self._safe_request("GET", url, timeout=API_TIMEOUT)
                if response.status_code in (301, 302, 307, 308, 404, 405, 422):
                    continue
                self.raise_for_api_error(response)
                data = response.json()
                if isinstance(data, list):
                    return data
                if isinstance(data, dict):
                    res = data.get("files") or data.get("user_files") or data.get("data")
                    if isinstance(res, list):
                        return res
            except Exception as exc:
                logger.debug("Endpoint %s for project files failed: %s", url, exc)
                continue
        return []

    def create_project(self, name: str, description: str = "") -> Dict[str, Any]:
        payload = {"name": name, "description": description}
        params = {"name": name, "description": description}
        endpoints = [
            f"{self.danswer_url}/api/user/projects/create",
        ]
        last_exc = None
        for url in endpoints:
            try:
                response = self._safe_request(
                    "POST",
                    url,
                    json=payload,
                    params=params,
                    timeout=API_TIMEOUT,
                )
                if response.status_code in (301, 302, 307, 308, 404, 405, 422):
                    continue
                self.raise_for_api_error(response)
                return response.json()
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc:
            raise last_exc
        return {"id": name, "name": name}

    def delete_project_file(self, file_id: str, project_id: str = "") -> None:
        """Delete an existing Onyx project file by its file ID."""
        fid = (file_id or "").strip()
        pid = (project_id or "").strip()
        if not fid:
            return

        urls = [
            f"{self.danswer_url}/api/user/projects/file/{fid}",
        ]
        if pid:
            urls.append(f"{self.danswer_url}/api/user/projects/{pid}/files/{fid}")

        for url in urls:
            try:
                response = self._safe_request("DELETE", url, timeout=API_TIMEOUT)
                if response.status_code in (200, 204, 404):
                    logger.debug("Delete project file endpoint %s returned %s", url, response.status_code)
                else:
                    self.raise_for_api_error(response)
            except Exception as exc:
                logger.debug("Non-fatal exception while deleting file %s at %s: %s", fid, url, exc)

        logger.info("Executed deletion cleanup for file_id=%s", fid)
        get_run_logger().log_action(
            category="FILE_DELETE",
            action="DELETE_PROJECT_FILE",
            details={"file_id": fid, "project_id": pid},
        )

    def upload_project_file(
        self, project_id: Any, filename: str, content_bytes: bytes
    ) -> Dict[str, Any]:
        pid_str = str(project_id).strip() if project_id is not None else ""
        pid_val = int(pid_str) if pid_str.isdigit() else pid_str
        url = f"{self.danswer_url}/api/user/projects/file/upload"

        upload_name = filename if filename.endswith(".txt") else f"{filename}.txt"
        files = {"files": (upload_name, content_bytes, "text/plain")}
        data = {
            "project_id": pid_val if pid_val else "",
            "temp_id_map": "{}",
        }
        params = {"project_id": pid_val} if pid_val else {}

        try:
            response = self._safe_request(
                "POST",
                url,
                files=files,
                data=data,
                params=params,
                timeout=API_TIMEOUT,
            )

            if response.status_code == 422 and pid_str.isdigit():
                data["project_id"] = int(pid_str)
                params["project_id"] = int(pid_str)
                response = self._safe_request(
                    "POST",
                    url,
                    files={"files": (upload_name, content_bytes, "text/plain")},
                    data=data,
                    params=params,
                    timeout=API_TIMEOUT,
                )
            elif response.status_code == 422 and isinstance(pid_val, int):
                data["project_id"] = str(pid_val)
                params["project_id"] = str(pid_val)
                response = self._safe_request(
                    "POST",
                    url,
                    files={"files": (upload_name, content_bytes, "text/plain")},
                    data=data,
                    params=params,
                    timeout=API_TIMEOUT,
                )

            self.raise_for_api_error(response)
            res_data = response.json()
            ret_dict = {}
            if isinstance(res_data, dict):
                rejected = res_data.get("rejected_files")
                if isinstance(rejected, list) and rejected:
                    logger.warning("Onyx rejected file '%s': %s", upload_name, rejected)
                user_files = res_data.get("user_files")
                ret = None
                if isinstance(user_files, list) and user_files:
                    ret = user_files[0]
                else:
                    ret = res_data.get("file_descriptor") or res_data.get("file") or res_data.get("data") or res_data
                if isinstance(ret, dict):
                    if not ret.get("type"):
                        ret["type"] = ret.get("chat_file_type") or "plain_text"
                    ret_dict = ret
            elif isinstance(res_data, list) and res_data:
                ret = res_data[0]
                if isinstance(ret, dict) and not ret.get("type"):
                    ret["type"] = ret.get("chat_file_type") or "plain_text"
                ret_dict = ret if isinstance(ret, dict) else {}

            if not ret_dict:
                raise RuntimeError(
                    f"Onyx upload response for '{upload_name}' contained no file descriptor: {str(res_data)[:500]}"
                )

            # Normalize: keep both id keys as returned by Onyx (UserFileSnapshot
            # carries "id" = user-file UUID and "file_id" = blob string).
            get_run_logger().log_file_upload(
                file_path=filename,
                canonical_name=upload_name,
                file_id=str(ret_dict.get("file_id") or ret_dict.get("id") or ""),
                project_id=pid_str,
                status="UPLOADED",
            )
            return ret_dict
        except Exception as exc:
            logger.warning("Upload project file '%s' failed on %s: %s", upload_name, url, exc)
            get_run_logger().log_file_upload(
                file_path=filename,
                canonical_name=upload_name,
                project_id=pid_str,
                status="FAILED",
                error=str(exc),
            )
            raise

    def delete_chat_session(self, session_id: str, kind: str = "unknown") -> None:
        response = self.session.delete(
            f"{self.danswer_url}/api/chat/delete-chat-session/{session_id}",
            timeout=API_TIMEOUT,
        )
        self.raise_for_api_error(response)
        session_registry.unregister(session_id, kind)
        get_run_logger().log_action(
            category="SESSION",
            action="DELETE_CHAT_SESSION",
            details={"session_id": session_id, "kind": kind},
        )

    @staticmethod
    def extract_tool_ids(tools: Any) -> List[int]:
        tool_list = tools if isinstance(tools, list) else tools.get("tools", []) if isinstance(tools, dict) else []
        result = []
        for tool in tool_list:
            if not isinstance(tool, dict):
                continue
            tool_id = tool.get("id")
            if tool_id is None:
                continue
            try:
                result.append(int(tool_id))
            except (TypeError, ValueError):
                continue
        return result

    def create_chat_session(
        self,
        persona_id: int,
        project_id: Optional[Any] = None,
        kind: str = "segment",
    ) -> str:
        session_uid = uuid4().hex[:8]
        session_name = f"llmproxy: {session_uid}"

        pid_val = int(project_id) if isinstance(project_id, str) and project_id.isdigit() else project_id

        payload = {
            "persona_id": persona_id,
            "description": session_name,
            "project_id": pid_val,
        }

        logger.info("Creating Onyx session name=%s persona_id=%s project_id=%s kind=%s", session_name, persona_id, project_id, kind)

        response = self.session.post(
            f"{self.danswer_url}/api/chat/create-chat-session",
            json=payload,
            timeout=API_TIMEOUT,
        )
        self.raise_for_api_error(response)

        data = response.json()
        session_id = data.get("chat_session_id")
        if not session_id:
            raise RuntimeError(f"Onyx response did not contain chat_session_id: {data}")

        session_id_str = str(session_id)
        session_registry.register(session_id_str, kind)
        get_run_logger().log_action(
            category="SESSION",
            action="CREATE_CHAT_SESSION",
            details={
                "session_id": session_id_str,
                "persona_id": persona_id,
                "project_id": project_id,
                "kind": kind,
            },
        )
        return session_id_str

    @staticmethod
    def extract_local_tool_invocation(answer: str) -> Optional[dict]:
        return extract_local_tool_invocation(answer)

    @staticmethod
    def extract_all_local_tool_invocations(answer: str) -> List[dict]:
        return extract_all_local_tool_invocations(answer)

    def send_message(
        self,
        session_id: str,
        message: str,
        stream: bool,
        temperature: float = 0.3,
        allowed_tool_ids: Optional[List[int]] = None,
        file_descriptors: Optional[List[dict]] = None,
        model: str = REAL_TALK_MODEL,
        disable_search: bool = False,
    ) -> requests.Response:
        sanitized_descriptors: List[Dict[str, Any]] = []
        for fd in (file_descriptors or []):
            if isinstance(fd, dict) and (fd.get("id") or fd.get("file_id")):
                f_id = str(fd.get("id") or fd.get("file_id"))
                f_type = fd.get("type") or fd.get("chat_file_type") or "plain_text"
                if f_type == "text/plain":
                    f_type = "plain_text"
                sanitized_descriptors.append({
                    "id": f_id,
                    "type": f_type,
                    "name": fd.get("name") or "",
                    **({"user_file_id": str(fd["user_file_id"])} if fd.get("user_file_id") else {}),
                })

        payload: Dict[str, Any] = {
            "message": message,
            "chat_session_id": session_id,
            "file_descriptors": sanitized_descriptors,
            "internal_search_filters": None if disable_search else {"source_type": ["web", "file"]},
            "search_doc_ids": [] if disable_search else None,
            "deep_research": False,
            "stream": stream,
            "include_citations": False,
        }
        if model is not None:
            payload["llm_override"] = {
                "temperature": temperature,
                "model_provider": MODELS[model][1],
                "model_version": MODELS[model][2],
            }

        if allowed_tool_ids is not None:
            payload["allowed_tool_ids"] = allowed_tool_ids

        logger.info(
            "Sending Onyx message session_id=%s stream=%s message_length=%s active_descriptors=%d",
            session_id,
            stream,
            len(message),
            len(sanitized_descriptors),
        )

        get_run_logger().log_llm_request(
            model=model,
            session_id=session_id,
            message=message,
            temperature=temperature,
            allowed_tools=allowed_tool_ids,
            descriptors=sanitized_descriptors,
            extra={"stream": stream, "disable_search": disable_search},
        )

        response = self.session.post(
            f"{self.danswer_url}/api/chat/send-chat-message",
            json=payload,
            timeout=API_TIMEOUT,
            stream=stream,
        )
        self.raise_for_api_error(response)
        return response

    @staticmethod
    def extract_complete_answer(response: requests.Response) -> str:
        data = response.json()
        if data.get("error_msg"):
            raise RuntimeError(str(data["error_msg"]))

        answer = data.get("answer") or data.get("answer_citationless") or data.get("content")
        if answer is None:
            raise RuntimeError(f"Onyx response did not contain an answer: {data}")

        return str(answer)

    @staticmethod
    def iter_stream_text(response: requests.Response) -> Iterator[str]:
        line_count = 0
        for raw_line in response.iter_lines(decode_unicode=True):
            if not raw_line:
                continue
            line = raw_line.strip()
            line_count += 1
            if line_count <= 15 or line_count % 20 == 0:
                logger.info("DEBUG STREAM line_count=%d: %s", line_count, line[:200])
            if line.startswith("data:"):
                line = line[5:].strip()
            if line == "[DONE]":
                break
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                logger.info("DEBUG STREAM json error on line_count=%d: %r", line_count, line[:150])
                continue

            if not isinstance(event, dict):
                continue

            err_msg = event.get("error") or event.get("error_msg") or event.get("message")
            obj = event.get("obj")
            if isinstance(obj, dict):
                err_msg = err_msg or obj.get("error") or obj.get("error_msg") or obj.get("message")
                event_type = obj.get("type")
            else:
                obj = {}
                event_type = event.get("type")

            if event_type == "error" or "error" in event:
                if err_msg:
                    raise RuntimeError(f"Onyx streaming error: {err_msg}")

            chunk_text = ""
            if "answer_piece" in event:
                chunk_text = event["answer_piece"]
            elif "answer_piece" in obj:
                chunk_text = obj["answer_piece"]
            elif "content" in event:
                chunk_text = event["content"]
            elif "content" in obj:
                chunk_text = obj["content"]
            elif "delta" in event and isinstance(event["delta"], dict) and "content" in event["delta"]:
                chunk_text = event["delta"]["content"]
            elif "delta" in obj and isinstance(obj["delta"], dict) and "content" in obj["delta"]:
                chunk_text = obj["delta"]["content"]

            if isinstance(chunk_text, str) and chunk_text:
                yield chunk_text
