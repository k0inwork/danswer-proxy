"""
Integration tests for Flask OpenAI API routes (/health, /v1/models, /v1/chat/completions)
and completion chunk utilities.
"""

import importlib
import json
from unittest.mock import MagicMock, patch
import pytest
import orchestrator.server as server_mod


@pytest.fixture(autouse=True)
def setup_server_routes():
    if isinstance(server_mod.health, MagicMock):
        server_mod.app.route = lambda *a, **kw: (lambda fn: fn)
        importlib.reload(server_mod)


def test_make_completion_chunk():
    chunk = server_mod.make_completion_chunk(
        completion_id="chatcmpl-123",
        content="Hello",
        role="assistant",
        finish_reason=None,
    )
    assert chunk["id"] == "chatcmpl-123"
    assert chunk["object"] == "chat.completion.chunk"
    assert chunk["choices"][0]["delta"]["content"] == "Hello"


def test_health_handler():
    health_data = server_mod.health()
    assert health_data["status"] == "ok"
    assert "version" in health_data


def test_list_models_handler():
    res = server_mod.list_models()
    assert res is not None
    data = json.loads(res.get_data(as_text=True))
    model_ids = [m["id"] for m in data["data"]]
    assert "claude-sonnet-4.6" in model_ids
    assert "glm-4" in model_ids
    assert "gpt-4" not in model_ids
    assert "claude-3-opus-20240229" not in model_ids


def test_chat_completions_handler_uninitialized():
    with patch.object(server_mod, "orchestrator", None):
        res = server_mod.chat_completions()
        assert res[1] == 503
        assert res[0]["error"] == "Orchestrator is not initialized"


def test_chat_completions_non_streaming_multi_tool():
    mock_orchestrator = MagicMock()
    mock_orchestrator.process_query.return_value = iter([
        "Let me check two files:\n",
        '<local_tool><name>read_file</name><arguments>{"file_path": "a.txt"}</arguments></local_tool>\n',
        '<local_tool><name>read_file</name><arguments>{"file_path": "b.txt"}</arguments></local_tool>'
    ])

    with patch.object(server_mod, "orchestrator", mock_orchestrator):
        with server_mod.app.test_request_context(
            "/v1/chat/completions",
            method="POST",
            json={
                "messages": [{"role": "user", "content": "read a and b"}],
                "stream": False,
            },
        ):
            res = server_mod.chat_completions()
            data = json.loads(res.get_data(as_text=True))
            assert "choices" in data
            msg = data["choices"][0]["message"]
            assert len(msg["tool_calls"]) == 2
            assert msg["tool_calls"][0]["index"] == 0
            assert msg["tool_calls"][0]["function"]["name"] == "read_file"
            assert msg["tool_calls"][1]["index"] == 1
            assert msg["tool_calls"][1]["function"]["name"] == "read_file"
            assert data["choices"][0]["finish_reason"] == "tool_calls"
