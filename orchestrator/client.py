"""
Resilient HTTP client for Onyx / Danswer API with retry adapters and SSE streams.
"""

import json
from typing import Any, Dict, Iterator, List, Optional
from uuid import uuid4

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from orchestrator.config import (
    API_TIMEOUT,
    MODELS,
    REAL_TALK_MODEL,
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
        except requests.HTTPError as exc:
            raise RuntimeError(
                f"Onyx API error {response.status_code}: {response.text[:4000]}"
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

    def attach_file_to_project(self, project_id: str, file_id: str) -> bool:
        """Links an uploaded file_id to a project_id across candidate Onyx endpoints."""
        pid = (project_id or "").strip()
        fid = (file_id or "").strip()
        if not pid or not fid:
            return False

        endpoints = [
            f"{self.danswer_url}/api/user/projects/{pid}/files/{fid}",
        ]

        for ep in endpoints:
            try:
                res = self._safe_request("POST", ep, timeout=API_TIMEOUT)
                if res.status_code in (200, 201, 204):
                    return True
                elif res.status_code in (400, 404, 405, 409):
                    logger.debug("Project association returned code %s (treating as auto-attached or candidate skipped)", res.status_code)
                    return True
                else:
                    logger.warning("Attachment to project request %s returned code %s", ep, res.status_code)
            except Exception as exc:
                logger.debug("Failed endpoint %s: %s", ep, exc)
                continue

        return True

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

    def upload_project_file(
        self, project_id: str, filename: str, content_bytes: bytes
    ) -> Dict[str, Any]:
        pid = (project_id or "").strip()
        url = f"{self.danswer_url}/api/user/projects/file/upload"

        upload_name = filename if filename.endswith(".txt") else f"{filename}.txt"
        files = {"files": (upload_name, content_bytes, "text/plain")}
        data = {
            "project_id": str(pid) if pid else "",
            "temp_id_map": "{}",
        }

        try:
            response = self._safe_request(
                "POST",
                url,
                files=files,
                data=data,
                timeout=API_TIMEOUT,
            )

            if response.status_code == 422 and pid.isdigit():
                data["project_id"] = int(pid)
                response = self._safe_request(
                    "POST",
                    url,
                    files={"files": (upload_name, content_bytes, "text/plain")},
                    data=data,
                    timeout=API_TIMEOUT,
                )

            self.raise_for_api_error(response)
            res_data = response.json()
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
                    return ret
            if isinstance(res_data, list) and res_data:
                ret = res_data[0]
                if isinstance(ret, dict) and not ret.get("type"):
                    ret["type"] = ret.get("chat_file_type") or "plain_text"
                return ret
            return {"id": upload_name, "name": upload_name, "type": "plain_text"}
        except Exception as exc:
            logger.warning("Upload project file '%s' failed on %s: %s", upload_name, url, exc)
            raise

    def delete_chat_session(self, session_id: str, kind: str = "unknown") -> None:
        response = self.session.delete(
            f"{self.danswer_url}/api/chat/delete-chat-session/{session_id}",
            timeout=API_TIMEOUT,
        )
        self.raise_for_api_error(response)
        session_registry.unregister(session_id, kind)

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
        project_id: Optional[str] = None,
        kind: str = "segment",
    ) -> str:
        session_uid = uuid4().hex[:8]
        session_name = f"llmproxy: {session_uid}"

        payload = {
            "persona_id": persona_id,
            "description": session_name,
            "project_id": project_id,
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
            "llm_override": {
                "temperature": temperature,
                "model_provider": MODELS[model][1],
                "model_version": MODELS[model][2],
            },
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
