"""
Thread-safe conversation store for active segments, compacting context, and detector sessions.
"""

from threading import Lock
from typing import Any, Dict, List, Optional

from orchestrator.config import GENERAL_PERSONA_ID, log_session_event, logger
from orchestrator.models import Segment


class ConversationStore:
    def __init__(self, client: Any):
        self._lock = Lock()
        self.client = client
        self._segments: Dict[str, List[Segment]] = {}
        self._detector_sessions: Dict[str, str] = {}
        self._next_segment_id = 1

    def get_active(self, conversation_id: str) -> Optional[Segment]:
        with self._lock:
            segments = self._segments.get(conversation_id, [])
            return segments[-1] if segments else None

    def get_or_create_detector_session(self, conversation_id: str) -> str:
        with self._lock:
            if conversation_id not in self._detector_sessions:
                session_id = self.client.create_chat_session(GENERAL_PERSONA_ID, kind="detector")
                self._detector_sessions[conversation_id] = session_id
            return self._detector_sessions[conversation_id]

    def reset_detector_session(self, conversation_id: str) -> None:
        with self._lock:
            session_id = self._detector_sessions.pop(conversation_id, None)

        if session_id:
            try:
                self.client.delete_chat_session(session_id, kind="detector_reset")
            except Exception as e:
                logger.warning("Failed to delete remote detector session=%s: %s", session_id, e)

    def create_segment(
        self,
        conversation_id: str,
        persona_id: int,
        project_id: Optional[str] = None,
        inherited_context: str = "",
    ) -> Segment:
        with self._lock:
            session_id = self.client.create_chat_session(
                persona_id=persona_id,
                project_id=project_id,
                kind="segment",
            )
            segment = Segment(
                segment_id=self._next_segment_id,
                persona_id=persona_id,
                session_id=session_id,
                inherited_context=inherited_context,
            )
            self._next_segment_id += 1
            self._segments.setdefault(conversation_id, []).append(segment)

            log_session_event(
                event="CREATED_SEGMENT",
                conversation_id=conversation_id,
                session_id=segment.session_id,
                persona_id=persona_id,
            )
            return segment

    def close_active(self, conversation_id: str, compaction: str) -> Optional[Segment]:
        with self._lock:
            segments = self._segments.get(conversation_id, [])
            if not segments:
                return None

            segment = segments[-1]
            segment.compaction = compaction
            segment.status = "CLOSED"

            log_session_event(
                event="CLOSED_SEGMENT",
                conversation_id=conversation_id,
                session_id=segment.session_id,
                persona_id=segment.persona_id,
            )

            try:
                self.client.delete_chat_session(segment.session_id, kind="segment")
                logger.info("Automatically erased Danswer session=%s", segment.session_id)
            except Exception as e:
                logger.warning("Failed to automatically erase session=%s: %s", segment.session_id, e)

            return segment

    def append_message(self, conversation_id: str, role: str, content: str) -> None:
        with self._lock:
            segments = self._segments.get(conversation_id, [])
            if segments:
                segments[-1].messages.append({"role": role, "content": content})

    def inherited_context(self, conversation_id: str) -> str:
        with self._lock:
            segments = self._segments.get(conversation_id, [])
            compacted = [segment.compaction for segment in segments if segment.compaction]
            return "\n\n---\n\n".join(compacted)
