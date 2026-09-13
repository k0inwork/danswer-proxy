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

    def _digests(self, *texts):
        import hashlib
        return [hashlib.sha256(t.encode()).hexdigest() for t in texts]

    def test_register_and_prefix_match(self):
        idx = self.cls(self.path)
        dd = self._digests("hello", "continue")
        conv = idx.register(dd[:1])
        # transcript grew by one message -> prefix match, same conversation
        self.assertEqual(idx.match(dd), conv)

    def test_exact_retry_matches(self):
        idx = self.cls(self.path)
        d1 = self._digests("hello")
        conv = idx.register(d1)
        self.assertEqual(idx.match(d1), conv)

    def test_no_match_for_different_history(self):
        idx = self.cls(self.path)
        idx.register(self._digests("hello"))
        self.assertIsNone(idx.match(self._digests("different question")))

    def test_no_match_when_incoming_is_shorter(self):
        idx = self.cls(self.path)
        d1, d2 = self._digests("a", "b")
        idx.register([d1, d2])
        self.assertIsNone(idx.match([d1]))

    def test_persistence_across_instances(self):
        d1 = self._digests("persist me")
        idx = self.cls(self.path)
        conv = idx.register(d1)
        idx2 = self.cls(self.path)
        self.assertEqual(idx2.match(d1), conv)
