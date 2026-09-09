"""
Unit tests verifying DanswerClient interactions with the Mock Onyx Server.
"""

import requests
from orchestrator.client import DanswerClient


def test_mock_onyx_permissions(mock_onyx_server):
    """Test fetching permissions from mock Onyx server."""
    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-token")
    resp = client.session.get(f"{client.danswer_url}/api/me/permissions")
    assert resp.status_code == 200
    data = resp.json()
    assert "permissions" in data
    assert "basic" in data["permissions"]


def test_mock_onyx_personas_and_tools(mock_onyx_server):
    """Test personas and tools endpoints."""
    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-token")
    personas = client.fetch_personas()
    assert isinstance(personas, list)
    assert len(personas) >= 2
    assert personas[0]["name"] == "General Assistant"

    tools = client.fetch_tools()
    assert isinstance(tools, list)
    tool_ids = client.extract_tool_ids(tools)
    assert tool_ids == [1, 2]


def test_mock_onyx_projects_and_files(mock_onyx_server):
    """Test user projects, project file upload, attachment, listing, and deletion."""
    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-token")

    # Projects
    projects = client.get_user_projects()
    assert len(projects) >= 1

    new_project = client.create_project(name="Test Suite Project", description="Testing")
    assert new_project["name"] == "Test Suite Project"
    pid = new_project["id"]

    # Upload file
    upload_res = client.upload_project_file(project_id=pid, filename="sample.txt", content_bytes=b"Hello Onyx")
    assert upload_res["id"].startswith("file-")
    fid = upload_res["id"]

    # Attach file
    attached = client.attach_file_to_project(project_id=pid, file_id=fid)
    assert attached is True

    # List project files
    pfiles = client.get_project_files(project_id=pid)
    assert any(f["id"] == fid for f in pfiles)

    # Delete project file
    client.delete_project_file(file_id=fid, project_id=pid)
    pfiles_after = client.get_project_files(project_id=pid)
    assert not any(f["id"] == fid for f in pfiles_after)


def test_mock_onyx_chat_session_and_message(mock_onyx_server):
    """Test creating chat session, sending non-streaming and streaming messages, and deleting chat session."""
    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-token")

    session_id = client.create_chat_session(persona_id=0, kind="test")
    assert session_id is not None

    # Sync non-streaming message
    sync_resp = client.send_message(
        session_id=session_id,
        message="What is the mock answer?",
        stream=False,
    )
    answer = client.extract_complete_answer(sync_resp)
    assert "Mock Onyx answer to: What is the mock answer?" in answer

    # Streaming message
    stream_resp = client.send_message(
        session_id=session_id,
        message="Stream me an answer",
        stream=True,
    )
    chunks = list(client.iter_stream_text(stream_resp))
    full_stream_answer = "".join(chunks)
    assert "Mock Onyx answer to: Stream me an answer" in full_stream_answer

    # Cleanup
    client.delete_chat_session(session_id)
