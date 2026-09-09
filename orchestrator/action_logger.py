"""
Explicit Action Logger for Onyx / Danswer Orchestrator.
Organizes logs by date and run ID in the `log/` directory, recording detailed
events for LLM requests, actions, file uploads, file reading, tool calls, and session lifecycle.
"""

from datetime import datetime
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional
from uuid import uuid4

# Target Python logger name used across the application
LOGGER_NAME = "danswer-orchestrator-v4"


class ActionLogger:
    """
    Manages structured action logging organized by date and run ID.
    Outputs to `log/YYYY-MM-DD/run_<run_id>/actions.log` and `run_info.json`.
    """

    def __init__(
        self,
        base_log_dir: str = "log",
        workspace_root: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        self.workspace_root = workspace_root or os.getcwd()
        self.proxy_root = os.getcwd()

        # Log directory resides in the proxy execution root (where proxy runs)
        if not os.path.isabs(base_log_dir):
            self.base_log_dir = os.path.abspath(os.path.join(self.proxy_root, base_log_dir))
        else:
            self.base_log_dir = base_log_dir

        self.start_time = datetime.now()
        self.date_str = self.start_time.strftime("%Y-%m-%d")
        self.time_str = self.start_time.strftime("%H%M%S")

        if run_id:
            self.run_id = run_id
        else:
            short_uuid = uuid4().hex[:6]
            self.run_id = f"{self.time_str}_{short_uuid}"

        self.run_dir = os.path.join(self.base_log_dir, self.date_str, f"run_{self.run_id}")
        os.makedirs(self.run_dir, exist_ok=True)

        self.actions_log_path = os.path.join(self.run_dir, "actions.log")
        self.daily_log_path = os.path.join(self.base_log_dir, f"{self.date_str}.log")
        self.datetimed_log_path = os.path.join(self.base_log_dir, f"{self.date_str}_{self.time_str}.log")
        self.run_info_path = os.path.join(self.run_dir, "run_info.json")

        self._file_handler: Optional[logging.FileHandler] = None
        self._daily_file_handler: Optional[logging.FileHandler] = None
        self._datetimed_file_handler: Optional[logging.FileHandler] = None
        self._setup_file_handler()
        self._write_run_info()

        self.log_action(
            category="RUN",
            action="START_RUN",
            details={
                "run_id": self.run_id,
                "date": self.date_str,
                "run_dir": self.run_dir,
                "workspace_root": self.workspace_root,
                "pid": os.getpid(),
            },
        )

    def _setup_file_handler(self) -> None:
        """Attaches FileHandlers for `actions.log`, `{date_str}.log`, and `{date_str}_{time_str}.log`."""
        app_logger = logging.getLogger(LOGGER_NAME)
        app_logger.setLevel(logging.INFO)

        actions_abs = os.path.abspath(self.actions_log_path)
        daily_abs = os.path.abspath(self.daily_log_path)
        datetimed_abs = os.path.abspath(self.datetimed_log_path)

        has_actions_handler = False
        has_daily_handler = False
        has_datetimed_handler = False

        for h in app_logger.handlers:
            if isinstance(h, logging.FileHandler):
                h_abs = os.path.abspath(getattr(h, "baseFilename", ""))
                if h_abs == actions_abs:
                    self._file_handler = h
                    has_actions_handler = True
                if h_abs == daily_abs:
                    self._daily_file_handler = h
                    has_daily_handler = True
                if h_abs == datetimed_abs:
                    self._datetimed_file_handler = h
                    has_datetimed_handler = True

        formatter = logging.Formatter(
            "%(asctime)s [%(levelname)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        if not has_actions_handler:
            file_handler = logging.FileHandler(self.actions_log_path, encoding="utf-8")
            file_handler.setLevel(logging.INFO)
            file_handler.setFormatter(formatter)
            app_logger.addHandler(file_handler)
            self._file_handler = file_handler

        if not has_daily_handler:
            daily_handler = logging.FileHandler(self.daily_log_path, encoding="utf-8")
            daily_handler.setLevel(logging.INFO)
            daily_handler.setFormatter(formatter)
            app_logger.addHandler(daily_handler)
            self._daily_file_handler = daily_handler

        if not has_datetimed_handler:
            datetimed_handler = logging.FileHandler(self.datetimed_log_path, encoding="utf-8")
            datetimed_handler.setLevel(logging.INFO)
            datetimed_handler.setFormatter(formatter)
            app_logger.addHandler(datetimed_handler)
            self._datetimed_file_handler = datetimed_handler

    def _write_run_info(self) -> None:
        """Writes initial run metadata to `run_info.json`."""
        run_info = {
            "run_id": self.run_id,
            "date": self.date_str,
            "start_time": self.start_time.isoformat(),
            "workspace_root": self.workspace_root,
            "actions_log": self.actions_log_path,
            "pid": os.getpid(),
        }
        try:
            with open(self.run_info_path, "w", encoding="utf-8") as f:
                json.dump(run_info, f, indent=2, ensure_ascii=False)
        except Exception as exc:
            sys.stderr.write(f"Failed to write run_info.json: {exc}\n")

    def format_details(self, details: Optional[Dict[str, Any]] = None) -> str:
        if not details:
            return ""
        items = []
        for k, v in details.items():
            if isinstance(v, (dict, list)):
                val_str = json.dumps(v, ensure_ascii=False)
            else:
                val_str = str(v)
            if len(val_str) > 500:
                val_str = val_str[:497] + "..."
            items.append(f"{k}={val_str}")
        return " | ".join(items)

    def log_action(
        self,
        category: str,
        action: str,
        details: Optional[Dict[str, Any]] = None,
        level: int = logging.INFO,
    ) -> None:
        """Generic explicit action logging method."""
        cat_str = category.upper()
        act_str = action.upper()
        det_str = self.format_details(details)

        message = f"[{cat_str}] [{act_str}]"
        if det_str:
            message += f" {det_str}"

        app_logger = logging.getLogger(LOGGER_NAME)
        app_logger.log(level, message)

    def log_llm_request(
        self,
        model: str,
        session_id: str,
        message: Any,
        temperature: Optional[float] = None,
        allowed_tools: Optional[List[int]] = None,
        descriptors: Optional[List[dict]] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Logs outbound or internal LLM request details."""
        msg_preview = str(message)
        if len(msg_preview) > 1000:
            msg_preview = msg_preview[:997] + "..."

        details: Dict[str, Any] = {
            "model": model,
            "session_id": session_id,
            "message_len": len(str(message)),
            "message_preview": msg_preview.replace("\n", " "),
        }

        if temperature is not None:
            details["temperature"] = temperature
        if allowed_tools is not None:
            details["allowed_tool_count"] = len(allowed_tools)
        if descriptors is not None:
            details["descriptor_count"] = len(descriptors)
        if extra:
            details.update(extra)

        self.log_action(category="LLM_REQUEST", action="SEND", details=details)

    def log_llm_response(
        self,
        model: str,
        session_id: str,
        response_summary: str,
        duration_ms: Optional[float] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Logs LLM response details or completions."""
        summary = str(response_summary).replace("\n", " ")
        if len(summary) > 1000:
            summary = summary[:997] + "..."

        details: Dict[str, Any] = {
            "model": model,
            "session_id": session_id,
            "response_summary": summary,
        }
        if duration_ms is not None:
            details["duration_ms"] = round(duration_ms, 2)
        if extra:
            details.update(extra)

        self.log_action(category="LLM_RESPONSE", action="RECEIVED", details=details)

    def log_file_upload(
        self,
        file_path: str,
        canonical_name: str,
        file_id: Optional[str] = None,
        project_id: Optional[str] = None,
        status: str = "PENDING",
        error: Optional[str] = None,
    ) -> None:
        """Logs workspace file upload and Onyx project attachment actions."""
        details: Dict[str, Any] = {
            "file_path": file_path,
            "canonical_name": canonical_name,
            "status": status,
        }
        if file_id:
            details["file_id"] = file_id
        if project_id:
            details["project_id"] = project_id
        if error:
            details["error"] = error

        self.log_action(category="FILE_UPLOAD", action="SYNC", details=details)

    def log_file_read(
        self,
        file_path: str,
        canonical_name: str,
        size_bytes: Optional[int] = None,
        revision: Optional[int] = None,
        source: str = "workspace_sync",
    ) -> None:
        """Logs workspace file reading and inspection events."""
        details: Dict[str, Any] = {
            "file_path": file_path,
            "canonical_name": canonical_name,
            "source": source,
        }
        if size_bytes is not None:
            details["size_bytes"] = size_bytes
        if revision is not None:
            details["revision"] = revision

        self.log_action(category="FILE_READ", action="INSPECT", details=details)

    def log_tool_call(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        result_summary: Optional[str] = None,
        intercepted: bool = False,
    ) -> None:
        """Logs tool invocation and execution details."""
        details: Dict[str, Any] = {
            "tool_name": tool_name,
            "arguments": arguments,
            "intercepted": intercepted,
        }
        if result_summary is not None:
            res = str(result_summary).replace("\n", " ")
            if len(res) > 500:
                res = res[:497] + "..."
            details["result"] = res

        action = "INTERCEPTED" if intercepted else "EXECUTE"
        self.log_action(category="TOOL_CALL", action=action, details=details)


# Module-level active logger instance
_ACTIVE_RUN_LOGGER: Optional[ActionLogger] = None


def get_run_logger() -> ActionLogger:
    """Returns the active ActionLogger instance, creating a default run if uninitialized."""
    global _ACTIVE_RUN_LOGGER
    if _ACTIVE_RUN_LOGGER is None:
        _ACTIVE_RUN_LOGGER = ActionLogger()
    return _ACTIVE_RUN_LOGGER


def init_run_logger(
    base_log_dir: str = "log",
    workspace_root: Optional[str] = None,
    run_id: Optional[str] = None,
    force_new: bool = False,
) -> ActionLogger:
    """Initializes or re-initializes the global ActionLogger instance."""
    global _ACTIVE_RUN_LOGGER
    if _ACTIVE_RUN_LOGGER is None or force_new:
        _ACTIVE_RUN_LOGGER = ActionLogger(
            base_log_dir=base_log_dir,
            workspace_root=workspace_root,
            run_id=run_id,
        )
    return _ACTIVE_RUN_LOGGER
