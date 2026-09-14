"""
Thread-safe conversation store for active segments, compacting context, and detector sessions.
"""

import hashlib
import json
import os
import re
import time
from threading import Lock
from typing import Any, Dict, List, Optional

from orchestrator.config import GENERAL_PERSONA_ID, log_session_event, logger
from orchestrator.models import Segment


class HistorySessionIndex:
    """Maps client chat histories to proxy conversation IDs for ID-less
    clients (e.g. openclaude) that resend the transcript each request.

    The client may rewrite earlier messages between turns (stripping
    ephemeral context), so exact digests never match. Instead a conversation
    is identified by the normalized head of its first user message plus the
    running user-message count: a request whose count is equal to or one
    more than the stored one (and with the same head) continues that
    conversation's Onyx session. The index is persisted so proxy restarts do
    not orphan open sessions."""

    MAX_ENTRIES = 50
    HEAD_CHARS = 200

    def __init__(self, cache_file: str):
        self.cache_file = cache_file
        self._lock = Lock()
        # conversation_id -> {"head": str, "count": int, "last_used": epoch}
        self._entries: Dict[str, Dict[str, Any]] = {}
        self._load()

    @classmethod
    def head_of(cls, messages: List[Dict[str, Any]]) -> str:
        """Normalized head (first user message, first HEAD_CHARS chars).

        Volatile blocks the client injects/rewrites between turns (e.g.
        <system-reminder>...) are stripped before hashing."""
        for m in messages or []:
            if isinstance(m, dict) and m.get("role") == "user":
                content = m.get("content")
                if not isinstance(content, str):
                    content = json.dumps(content, ensure_ascii=False, default=str)
                content = re.sub(r"<system-reminder>.*?</system-reminder>", "", content, flags=re.DOTALL)
                normalized = re.sub(r"\s+", " ", content).strip().lower()
                return hashlib.sha256(normalized[:cls.HEAD_CHARS].encode("utf-8")).hexdigest()
        return ""

    @classmethod
    def user_count(cls, messages: List[Dict[str, Any]]) -> int:
        return sum(1 for m in (messages or []) if isinstance(m, dict) and m.get("role") == "user")

    def _load(self) -> None:
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    self._entries = data
                logger.info("Loaded %d history session index entries from %s", len(self._entries), self.cache_file)
        except Exception as e:
            logger.warning("Failed to load history session index: %s", e)

    def _save(self) -> None:
        try:
            with open(self.cache_file, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning("Failed to save history session index: %s", e)

    def match(self, head: str, count: int) -> Optional[str]:
        """Return the conversation with the same head whose stored user count
        is <= the incoming count (continuation or client retry), or None."""
        if not head:
            return None
        with self._lock:
            best_id, best_count = None, -1
            for conv_id, entry in self._entries.items():
                if entry.get("head") != head:
                    continue
                stored_count = entry.get("count", 0)
                if stored_count <= count and stored_count > best_count:
                    best_id, best_count = conv_id, stored_count
            if best_id is not None:
                self._entries[best_id]["last_used"] = time.time()
                self._entries[best_id]["count"] = count
                self._save()
                logger.info(
                    "History match: reusing conversation %s (user message %d).", best_id, count
                )
            return best_id

    def register(self, head: str, count: int) -> str:
        """Register (or update) a conversation for a head/count pair and
        return its conversation ID."""
        with self._lock:
            # Reap stale entries beyond the cap (LRU by last_used)
            if len(self._entries) >= self.MAX_ENTRIES:
                oldest = min(self._entries, key=lambda k: self._entries[k].get("last_used", 0))
                self._entries.pop(oldest, None)
            conv_id = f"hist-{hashlib.sha256(head.encode()).hexdigest()[:12]}"
            self._entries[conv_id] = {"head": head, "count": count, "last_used": time.time()}
            self._save()
            return conv_id


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

    def discard_active(self, conversation_id: str, reason: str = "discarded") -> Optional[Segment]:
        """Mark the active segment CLOSED without touching Onyx.

        Used when the underlying Onyx session is already gone (e.g. deleted
        after an unrecoverable request failure) so the next turn of this
        conversation creates a fresh session instead of messaging a dead one."""
        with self._lock:
            segments = self._segments.get(conversation_id, [])
            if not segments:
                return None
            segment = segments[-1]
            segment.status = "CLOSED"
            log_session_event(
                event="DISCARDED_SEGMENT",
                conversation_id=conversation_id,
                session_id=segment.session_id,
                persona_id=segment.persona_id,
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
