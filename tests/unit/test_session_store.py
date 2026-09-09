"""
Unit tests for ConversationStore and segment management.
"""

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
