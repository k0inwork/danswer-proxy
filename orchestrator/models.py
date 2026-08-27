"""
Domain models and dataclasses for Onyx descriptors, sessions, and status tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from typing import Any, Dict, List, Optional, Set

from orchestrator.config import logger


class DescriptorStatus(Enum):
    PENDING_UPLOAD = "pending_upload"      # Local file changed/created, not in Onyx yet
    UPLOADED = "uploaded"                  # Uploaded to Onyx, awaiting explicit attachment to project
    READY = "ready"                        # Associated with project_id in Onyx; safe to attach
    FAILED = "failed"                      # Association or upload failed


@dataclass
class Descriptor:
    canonical_name: str
    file_path: str
    file_id: Optional[str] = None
    file_type: str = "plain_text"
    status: DescriptorStatus = DescriptorStatus.PENDING_UPLOAD
    project_id: Optional[str] = None
    error_message: Optional[str] = None

    def to_onyx_dict(self) -> Dict[str, Any]:
        return {
            "id": self.file_id or "",
            "type": self.file_type,
            "name": self.canonical_name,
        }


class SessionRegistry:
    def __init__(self):
        self._lock = Lock()
        self._active_sessions: Set[str] = set()

    def register(self, session_id: str, kind: str) -> None:
        with self._lock:
            self._active_sessions.add(session_id)
            logger.info("ONYX SESSION CREATED session_id=%s kind=%s", session_id, kind)

    def unregister(self, session_id: str, kind: str) -> None:
        with self._lock:
            self._active_sessions.discard(session_id)
            logger.info("ONYX SESSION DELETED session_id=%s kind=%s", session_id, kind)

    def get_all(self) -> List[str]:
        with self._lock:
            return list(self._active_sessions)

    def count(self) -> int:
        with self._lock:
            return len(self._active_sessions)


session_registry = SessionRegistry()


class Segment:
    def __init__(
        self,
        segment_id: int,
        persona_id: int,
        session_id: str,
        inherited_context: str = "",
    ):
        self.segment_id = segment_id
        self.persona_id = persona_id
        self.session_id = session_id
        self.inherited_context = inherited_context
        self.compaction: Optional[str] = None
        self.messages: List[Dict[str, str]] = []
        self.status = "ACTIVE"
