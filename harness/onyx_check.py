"""
Helper to inspect the real Onyx project state for a workspace directory.

Uses the same API semantics as the upstream Onyx backend:
- GET  /api/user/projects                       -> list of UserProjectSnapshot
- GET  /api/user/projects/files/{project_id}    -> bare list of UserFileSnapshot
- GET  /api/chat/file/{file_id}                 -> blob content (file_id = snapshot.file_id)
"""

from typing import Any, Dict, List, Optional

import hashlib
import requests


class OnyxChecker:
    def __init__(self, base_url: str, token: str):
        self.base = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Bearer {token}"})

    def _get_json(self, path: str) -> Any:
        # The Onyx server mis-issues absolute redirects to http://localhost for
        # slashless paths (same reason the proxy uses _safe_request), so never
        # follow redirects: retry the slashed path variant locally instead.
        candidates = [path, path.rstrip("/") + "/"] if not path.endswith("/") else [path, path.rstrip("/")]
        last = None
        for candidate in candidates:
            r = self.session.get(
                f"{self.base}{candidate}", timeout=60, allow_redirects=False
            )
            if r.status_code in (301, 302, 307, 308):
                last = r
                continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError(f"Onyx redirected all candidates for {path}: {last.status_code}")

    def find_project(self, name: str) -> Optional[Dict[str, Any]]:
        projects = self._get_json("/api/user/projects")
        if isinstance(projects, dict):
            projects = projects.get("projects") or []
        for p in projects:
            if isinstance(p, dict) and p.get("name") == name:
                return p
        return None

    def project_files(self, project_id: Any) -> List[Dict[str, Any]]:
        data = self._get_json(f"/api/user/projects/files/{project_id}")
        if isinstance(data, list):
            return [f for f in data if isinstance(f, dict)]
        if isinstance(data, dict):
            for key in ("files", "user_files", "data"):
                if isinstance(data.get(key), list):
                    return [f for f in data[key] if isinstance(f, dict)]
        return []

    def file_blob(self, file_id: str) -> str:
        r = self.session.get(
            f"{self.base}/api/chat/file/{file_id}", timeout=60, allow_redirects=False
        )
        r.raise_for_status()
        return r.text

    def project_overview(self, project_name: str) -> Dict[str, Any]:
        proj = self.find_project(project_name)
        if not proj:
            return {"exists": False}
        files = self.project_files(proj["id"])
        names = [f.get("name") or "" for f in files]
        return {
            "exists": True,
            "project_id": proj["id"],
            "file_names": names,
            "top_root_files": [n for n in names if n.startswith("TOP_FOLDER_")],
            "file_file_entries": [f for f in files if str(f.get("name", "")).startswith("FILE_")],
        }

    def fetch_synced_content(self, project_id: Any, canonical_name: str) -> Optional[str]:
        """Return the synced blob content for a canonical file name (newest snapshot)."""
        matches = [f for f in self.project_files(project_id) if f.get("name") == canonical_name]
        if not matches:
            return None
        blob_id = str(matches[-1].get("file_id") or "")
        if not blob_id:
            return None
        return self.file_blob(blob_id)

    @staticmethod
    def sha256(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]
