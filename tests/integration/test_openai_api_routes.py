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


def test_chat_completions_handler_uninitialized():
    with patch.object(server_mod, "orchestrator", None):
        res = server_mod.chat_completions()
        assert res[1] == 503
        assert res[0]["error"] == "Orchestrator is not initialized"
