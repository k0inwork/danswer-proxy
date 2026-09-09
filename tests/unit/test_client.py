"""
Unit tests for DanswerClient HTTP wrapper and response utilities.
"""

from unittest.mock import MagicMock
import pytest
import requests
from orchestrator.client import DanswerClient


def test_danswer_client_init():
    client = DanswerClient(danswer_url="http://localhost:8080/", api_token="test-token")
    assert client.danswer_url == "http://localhost:8080"
    assert client.session is not None


def test_raise_for_api_error_ok():
    response = MagicMock()
    response.raise_for_status.return_value = None
    DanswerClient.raise_for_api_error(response)


def test_raise_for_api_error_raises():
    response = MagicMock()
    response.status_code = 500
    response.text = "Internal Server Error"
    response.raise_for_status.side_effect = Exception("500 Server Error")
    with pytest.raises(RuntimeError) as exc_info:
        DanswerClient.raise_for_api_error(response)
    assert "Onyx API error 500" in str(exc_info.value)


def test_extract_tool_ids():
    tools = [
        {"id": 1, "name": "tool_1"},
        {"id": "2", "name": "tool_2"},
        {"id": None, "name": "invalid"},
    ]
    ids = DanswerClient.extract_tool_ids(tools)
    assert ids == [1, 2]


def test_extract_complete_answer():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answer": "Hello from Onyx!"}
    answer = DanswerClient.extract_complete_answer(mock_resp)
    assert answer == "Hello from Onyx!"


def test_extract_complete_answer_error():
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"error_msg": "Unauthorized"}
    with pytest.raises(RuntimeError) as exc_info:
        DanswerClient.extract_complete_answer(mock_resp)
    assert "Unauthorized" in str(exc_info.value)
