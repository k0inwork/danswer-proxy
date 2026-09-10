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


def test_create_chat_session_integer_project_id():
    client = DanswerClient(danswer_url="http://localhost:8080/", api_token="test-token")
    client.session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"chat_session_id": "sess-123"}
    client.session.post.return_value = mock_resp

    sid = client.create_chat_session(persona_id=0, project_id="63")
    assert sid == "sess-123"

    call_kwargs = client.session.post.call_args.kwargs
    assert call_kwargs["json"]["project_id"] == 63


from orchestrator.config import API_TIMEOUT


def test_attach_file_to_project_success():
    client = DanswerClient(danswer_url="http://localhost:8080/", api_token="test-token")
    client._safe_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    client._safe_request.return_value = mock_resp

    result = client.attach_file_to_project(project_id="63", file_id="fid-abc")
    assert result is True

    client._safe_request.assert_called_once_with(
        "POST",
        "http://localhost:8080/api/user/projects/63/files",
        json={"file_ids": ["fid-abc"], "file_id": "fid-abc"},
        timeout=API_TIMEOUT,
    )


def test_attach_file_to_project_failure_returns_false():
    client = DanswerClient(danswer_url="http://localhost:8080/", api_token="test-token")
    client._safe_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 404
    client._safe_request.return_value = mock_resp

    result = client.attach_file_to_project(project_id="63", file_id="fid-abc")
    assert result is False


def test_attach_file_to_project_skips_null_project_id_response():
    client = DanswerClient(danswer_url="http://localhost:8080/", api_token="test-token")
    client._safe_request = MagicMock()

    # Candidate 1 & 2 return HTTP 200 with project_id = None
    null_proj_resp = MagicMock()
    null_proj_resp.status_code = 200
    null_proj_resp.json.return_value = {"id": "user-file-uuid", "file_id": "proj-file-uuid", "project_id": None}

    client._safe_request.return_value = null_proj_resp
    client.get_project_files = MagicMock(return_value=[])

    result = client.attach_file_to_project(project_id="63", file_id="proj-file-uuid")
    assert result is False


def test_upload_project_file_returns_distinct_file_id():
    client = DanswerClient(danswer_url="http://localhost:8080/", api_token="test-token")
    client._safe_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "user_files": [
            {
                "id": "user-file-id-123",
                "file_id": "project-file-id-456",
                "name": "TOP_FOLDER_test.txt",
                "project_id": None,
            }
        ]
    }
    client._safe_request.return_value = mock_resp

    ret = client.upload_project_file(project_id=63, filename="TOP_FOLDER_test.txt", content_bytes=b"test")
    assert ret.get("id") == "user-file-id-123"
    assert ret.get("file_id") == "project-file-id-456"

    # Verify query params passed to request
    call_kwargs = client._safe_request.call_args[1]
    assert call_kwargs["params"] == {"project_id": 63}


def test_delete_project_file():
    client = DanswerClient(danswer_url="http://localhost:8080/", api_token="test-token")
    client._safe_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 204
    client._safe_request.return_value = mock_resp

    client.delete_project_file(file_id="fid-dup-1", project_id="63")
    assert client._safe_request.call_count == 2
