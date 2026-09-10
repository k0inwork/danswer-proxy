"""
Unit tests for /model command parsing, alias resolution, model listing, and switching.
"""

from unittest.mock import MagicMock
from orchestrator.config import MODELS, resolve_model_key
from orchestrator.core import Orchestrator


def test_resolve_model_key():
    assert resolve_model_key("glm") == "glm-4"
    assert resolve_model_key("glm-4") == "glm-4"
    assert resolve_model_key("glm4") == "glm-4"
    assert resolve_model_key("sonnet") == "claude-sonnet-4.6"
    assert resolve_model_key("claude-sonnet") == "claude-sonnet-4.6"
    assert resolve_model_key("claude-sonnet-4.6") == "claude-sonnet-4.6"
    assert resolve_model_key("gpt") == "gpt-5.4-nano"
    assert resolve_model_key("azure") == "azure-gpt54-nano"
    assert resolve_model_key("1") == "claude-sonnet-4.6"
    assert resolve_model_key("2") == "glm-4"
    assert resolve_model_key("invalid_model_123") is None


def test_parse_model_command():
    mock_client = MagicMock()
    orch = Orchestrator(client=mock_client, routing_manifest="", tool_ids=[])

    assert orch.parse_model_command("/model") == ("LIST", None)
    assert orch.parse_model_command("/models") == ("LIST", None)
    assert orch.parse_model_command("/model list") == ("LIST", None)
    assert orch.parse_model_command("model") == ("LIST", None)
    assert orch.parse_model_command("model list") == ("LIST", None)

    assert orch.parse_model_command("/model glm") == ("SWITCH", "glm")
    assert orch.parse_model_command("/model switch sonnet") == ("SWITCH", "sonnet")
    assert orch.parse_model_command("model: glm-4") == ("SWITCH", "glm-4")
    assert orch.parse_model_command("model=sonnet") == ("SWITCH", "sonnet")

    assert orch.parse_model_command("what is the model of this project?") is None
    assert orch.parse_model_command("can you write a data model for user?") is None


def test_handle_model_command_list_and_switch():
    mock_client = MagicMock()
    mock_client.create_chat_session.return_value = "sess-123"
    orch = Orchestrator(client=mock_client, routing_manifest="", tool_ids=[])
    cid = "test-conv-1"

    # Default model should be claude-sonnet-4.6
    assert orch.get_active_model(cid) == "claude-sonnet-4.6"

    # Test LIST command
    list_res = orch.handle_model_command(cid, "LIST")
    assert "Available Danswer models:" in list_res
    assert "Claude Sonnet 4.6" in list_res
    assert "GLM-4" in list_res
    assert "[ACTIVE]" in list_res

    # Test SWITCH command to GLM
    switch_glm = orch.handle_model_command(cid, "SWITCH", "glm")
    assert "Switched active Danswer model to GLM-4 (glm-4)" in switch_glm
    assert orch.get_active_model(cid) == "glm-4"

    # Test LIST command after switch
    list_after = orch.handle_model_command(cid, "LIST")
    assert "Current active model: GLM-4 (glm-4)" in list_after

    # Test SWITCH command back to Sonnet
    switch_sonnet = orch.handle_model_command(cid, "SWITCH", "sonnet")
    assert "Switched active Danswer model to Claude Sonnet 4.6 (claude-sonnet-4.6)" in switch_sonnet
    assert orch.get_active_model(cid) == "claude-sonnet-4.6"

    # Test SWITCH command with invalid target
    invalid_res = orch.handle_model_command(cid, "SWITCH", "nonexistent-model")
    assert "Unknown model 'nonexistent-model'" in invalid_res
    # Active model should remain unchanged
    assert orch.get_active_model(cid) == "claude-sonnet-4.6"


def test_process_query_model_command_interception():
    mock_client = MagicMock()
    mock_client.create_chat_session.return_value = "sess-456"
    orch = Orchestrator(client=mock_client, routing_manifest="", tool_ids=[])
    cid = "test-conv-2"

    messages = [{"role": "user", "content": "/model glm"}]
    chunks = list(orch.process_query(conversation_id=cid, messages=messages))

    assert len(chunks) == 1
    assert "Switched active Danswer model to GLM-4 (glm-4)" in chunks[0]
    assert orch.get_active_model(cid) == "glm-4"
    # Ensure Onyx API send_message was NOT called for model command interception
    mock_client.send_message.assert_not_called()


def test_process_query_uses_active_model():
    mock_client = MagicMock()
    mock_client.create_chat_session.return_value = "sess-789"
    mock_client.send_message.return_value = MagicMock()
    mock_client.iter_stream_text.return_value = ["Hello from GLM"]

    orch = Orchestrator(client=mock_client, routing_manifest="", tool_ids=[])
    cid = "test-conv-3"

    # Set active model to glm-4
    orch.set_active_model(cid, "glm-4")

    # Mock mode detector answer
    mock_client.send_message.return_value = MagicMock()
    mock_client.extract_complete_answer.return_value = "CONTINUE|0|reason"

    messages = [{"role": "user", "content": "Hello LLM"}]
    chunks = list(orch.process_query(conversation_id=cid, messages=messages))

    assert "".join(chunks) == "Hello from GLM"

    # Verify send_message was called with model="glm-4"
    send_calls = mock_client.send_message.call_args_list
    assert len(send_calls) >= 1
    last_call_kwargs = send_calls[-1][1]
    assert last_call_kwargs["model"] == "glm-4"
