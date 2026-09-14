"""
Unit tests for ConversationStore and segment management.
"""

import unittest
from unittest.mock import MagicMock
import pytest
from orchestrator.session_store import ConversationStore


def test_conversation_store_segment_lifecycle():
    mock_client = MagicMock()
    mock_client.create_chat_session.side_effect = ["sess_001", "sess_002"]

    store = ConversationStore(client=mock_client)

    # Initially no active segment
    assert store.get_active("conv-1") is None

    # Create first segment
    seg1 = store.create_segment("conv-1", persona_id=0, project_id="proj-123")
    assert seg1.segment_id == 1
    assert seg1.session_id == "sess_001"
    assert store.get_active("conv-1") == seg1

    # Append message
    store.append_message("conv-1", role="user", content="Hello")
    assert len(seg1.messages) == 1

    # Close active segment with compaction
    closed_seg = store.close_active("conv-1", compaction="User greeted system.")
    assert closed_seg == seg1
    assert closed_seg.status == "CLOSED"
    mock_client.delete_chat_session.assert_called_with("sess_001", kind="segment")

    # Inherited context
    inherited = store.inherited_context("conv-1")
    assert inherited == "User greeted system."

    # Create new segment
    seg2 = store.create_segment("conv-1", persona_id=5, project_id="proj-123", inherited_context=inherited)
    assert seg2.segment_id == 2
    assert seg2.persona_id == 5
    assert store.get_active("conv-1") == seg2


def test_detector_session_lifecycle():
    mock_client = MagicMock()
    mock_client.create_chat_session.return_value = "detector_sess_1"

    store = ConversationStore(client=mock_client)

    session_id = store.get_or_create_detector_session("conv-100")
    assert session_id == "detector_sess_1"

    # Second call returns cached session
    assert store.get_or_create_detector_session("conv-100") == "detector_sess_1"
    assert mock_client.create_chat_session.call_count == 1

    # Reset
    store.reset_detector_session("conv-100")
    mock_client.delete_chat_session.assert_called_with("detector_sess_1", kind="detector_reset")


class TestHistorySessionIndex(unittest.TestCase):
    def setUp(self):
        import os, tempfile
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        os.remove(path)
        self.path = path
        from orchestrator.session_store import HistorySessionIndex
        self.cls = HistorySessionIndex

    def tearDown(self):
        import os
        if os.path.exists(self.path):
            os.remove(self.path)

    def _msgs(self, *texts):
        out = []
        for t in texts:
            out.append({"role": "user", "content": t})
            out.append({"role": "assistant", "content": "ok"})
        return out

    def test_register_and_continuation_match(self):
        idx = self.cls(self.path)
        m1 = self._msgs("please read the file foo.py and tell me things")
        conv = idx.register(self.cls.head_of(m1), self.cls.user_count(m1))
        # turn 2: client rewrites the first message slightly (trailing context
        # stripped) and adds a second user message -> still matches
        m2 = self._msgs("please read the file foo.py and tell me things", "now edit it")
        m2[0]["content"] = m2[0]["content"] + "\n<system-reminder>ephemeral</system-reminder>"
        self.assertEqual(idx.match(self.cls.head_of(m2), self.cls.user_count(m2)), conv)

    def test_exact_retry_matches(self):
        idx = self.cls(self.path)
        m1 = self._msgs("hello there")
        conv = idx.register(self.cls.head_of(m1), self.cls.user_count(m1))
        self.assertEqual(idx.match(self.cls.head_of(m1), self.cls.user_count(m1)), conv)

    def test_no_match_for_different_history(self):
        idx = self.cls(self.path)
        m1 = self._msgs("question about databases")
        idx.register(self.cls.head_of(m1), self.cls.user_count(m1))
        m2 = self._msgs("completely different question about cooking")
        self.assertIsNone(idx.match(self.cls.head_of(m2), self.cls.user_count(m2)))

    def test_no_match_when_incoming_count_is_lower(self):
        idx = self.cls(self.path)
        m2 = self._msgs("first", "second")
        idx.register(self.cls.head_of(m2), self.cls.user_count(m2))
        m1 = self._msgs("first")
        self.assertIsNone(idx.match(self.cls.head_of(m1), self.cls.user_count(m1)))

    def test_persistence_across_instances(self):
        m1 = self._msgs("persist me")
        idx = self.cls(self.path)
        conv = idx.register(self.cls.head_of(m1), self.cls.user_count(m1))
        idx2 = self.cls(self.path)
        self.assertEqual(idx2.match(self.cls.head_of(m1), self.cls.user_count(m1)), conv)
