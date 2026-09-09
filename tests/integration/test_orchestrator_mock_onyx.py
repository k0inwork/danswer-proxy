"""
End-to-end integration tests connecting Orchestrator and WorkspaceProjectSync
directly to the live Mock Onyx server.
"""

import os
import json
import tempfile
import pytest
import orchestrator.server as server_mod
from orchestrator.client import DanswerClient
from orchestrator.core import Orchestrator
from orchestrator.matrix_manager import MatrixManager
from orchestrator.workspace_sync import WorkspaceProjectSync


def test_orchestrator_e2e_with_mock_onyx(mock_onyx_server, tmp_path):
    """
    Test full Orchestrator and WorkspaceProjectSync integration with Mock Onyx Server.
    """
    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-token")

    # 1. Test matrix manager against mock server
    matrix_manager = MatrixManager(client=client, cache_file=str(tmp_path / "matrix_cache.json"))
    manifest, tool_ids = matrix_manager.get_or_build_matrix(force_refresh=True)
    assert isinstance(manifest, str)
    assert tool_ids == [1, 2]

    # 2. Test workspace sync against mock server
    ws_sync = WorkspaceProjectSync(workspace_root=str(tmp_path), client=client)
    ws_sync.initialize_project()
    assert ws_sync.project_id is not None
    assert ws_sync.project_id.startswith("proj-")

    # 3. Create sample workspace file and perform blocking upload
    sample_file = tmp_path / "src" / "main.py"
    sample_file.parent.mkdir(parents=True, exist_ok=True)
    sample_file.write_text("print('hello mock onyx')", encoding="utf-8")

    desc = ws_sync.upload_and_attach_blocking("src/main.py")
    assert desc is not None
    assert desc.file_id.startswith("file-")

    ready_descriptors = ws_sync.get_ready_descriptors()
    assert len(ready_descriptors) >= 1
    assert any(d["id"] == desc.file_id for d in ready_descriptors)

    # 4. Initialize Orchestrator with mock client and workspace sync
    orch = Orchestrator(
        client=client,
        routing_manifest=manifest,
        tool_ids=tool_ids,
        workspace_sync=ws_sync,
    )

    # 5. Process query through Orchestrator
    messages = [{"role": "user", "content": "Hello Mock Onyx!"}]
    chunks = list(orch.process_query(conversation_id="conv-mock-1", messages=messages))
    full_response = "".join(chunks)
    assert "Mock Onyx answer to:" in full_response
    assert "Hello Mock Onyx!" in full_response

    # Clean up background watcher and executor
    ws_sync.stop_background_watcher()
    ws_sync.executor.shutdown(wait=True)


def test_repeat_run_same_project_top_folder_handling(mock_onyx_server, tmp_path):
    """
    Test that running WorkspaceProjectSync multiple times in the same folder:
    1. Uses the same project name formatted as workspace-<fullpathhash to folder>.
    2. Reuses the same project_id in Onyx across runs.
    3. Does not create additional TOP_FOLDER_... files in the project.
    4. Rewrites/replaces the old TOP_FOLDER_... file when directory contents change.
    """
    import hashlib

    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-token")
    root_str = os.path.abspath(str(tmp_path))
    expected_hash = hashlib.md5(root_str.encode("utf-8")).hexdigest()
    expected_project_name = f"workspace-{expected_hash}"

    # Run 1: First initialization
    ws_sync1 = WorkspaceProjectSync(workspace_root=root_str, client=client)
    assert ws_sync1.project_name == expected_project_name

    ws_sync1.initialize_project()
    project_id_1 = ws_sync1.project_id
    assert project_id_1 is not None

    ws_sync1.executor.shutdown(wait=True)
    ws_sync1.stop_background_watcher()

    # Verify project files in mock server after Run 1
    p_files_1 = client.get_project_files(project_id_1)
    top_folder_files_1 = [f for f in p_files_1 if f.get("name", "").startswith("TOP_FOLDER_")]
    assert len(top_folder_files_1) == 1

    # Run 2: Second run on the same folder
    ws_sync2 = WorkspaceProjectSync(workspace_root=root_str, client=client)
    assert ws_sync2.project_name == expected_project_name

    ws_sync2.initialize_project()
    project_id_2 = ws_sync2.project_id
    assert project_id_2 == project_id_1, "Repeat run in same dir should reuse same project_id"

    ws_sync2.executor.shutdown(wait=True)
    ws_sync2.stop_background_watcher()

    # Verify project files in mock server after Run 2
    p_files_2 = client.get_project_files(project_id_2)
    top_folder_files_2 = [f for f in p_files_2 if f.get("name", "").startswith("TOP_FOLDER_")]
    assert len(top_folder_files_2) == 1, "Should NOT create additional top_folder file"

    # Modify workspace contents and trigger update_top_folder
    new_file = tmp_path / "new_file.py"
    new_file.write_text("print('new file')", encoding="utf-8")

    ws_sync3 = WorkspaceProjectSync(workspace_root=root_str, client=client)
    ws_sync3.initialize_project()
    ws_sync3.update_top_folder()
    ws_sync3.executor.shutdown(wait=True)
    ws_sync3.stop_background_watcher()

    p_files_3 = client.get_project_files(project_id_1)
    top_folder_files_3 = [f for f in p_files_3 if f.get("name", "").startswith("TOP_FOLDER_")]
    assert len(top_folder_files_3) == 1, "Rewriting top_folder should replace old file, keeping count at 1"


def test_flask_routes_with_mock_onyx(mock_onyx_server, tmp_path):
    """
    Test Flask API route /v1/chat/completions with orchestrator initialized against mock_onyx_server.
    """
    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-token")
    matrix_manager = MatrixManager(client=client, cache_file=str(tmp_path / "cache.json"))
    manifest, tool_ids = matrix_manager.get_or_build_matrix(force_refresh=True)

    ws_sync = WorkspaceProjectSync(workspace_root=str(tmp_path), client=client)
    ws_sync.initialize_project()

    orch = Orchestrator(
        client=client,
        routing_manifest=manifest,
        tool_ids=tool_ids,
        workspace_sync=ws_sync,
    )

    # Inject orchestrator and client into server module
    server_mod.client = client
    server_mod.orchestrator = orch

    flask_app = server_mod.app
    flask_app.config["TESTING"] = True
    test_client = flask_app.test_client()

    # 1. Non-streaming completion with explicit conversation_id header
    res = test_client.post(
        "/v1/chat/completions",
        headers={"X-Conversation-ID": "conv-non-stream-123"},
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Testing Flask route"}],
            "stream": False,
        },
    )
    assert res.status_code == 200
    data = res.get_json()
    assert data["object"] == "chat.completion"
    content = data["choices"][0]["message"]["content"]
    assert "Mock Onyx answer to:" in content

    # 2. Streaming completion with explicit conversation_id header
    stream_res = test_client.post(
        "/v1/chat/completions",
        headers={"X-Conversation-ID": "conv-stream-456"},
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "Testing streaming route"}],
            "stream": True,
        },
    )
    assert stream_res.status_code == 200
    assert "text/event-stream" in stream_res.content_type

    raw_sse = stream_res.get_data(as_text=True)
    assert "data: {" in raw_sse
    assert "[DONE]" in raw_sse

    content_pieces = []
    for line in raw_sse.splitlines():
        if line.startswith("data: ") and "[DONE]" not in line:
            data_dict = json.loads(line[6:])
            choices = data_dict.get("choices", [])
            if choices and "delta" in choices[0]:
                content_pieces.append(choices[0]["delta"].get("content", ""))
    reconstructed = "".join(content_pieces)

    assert "Mock Onyx" in reconstructed
    assert "streaming route" in reconstructed

    # Clean up background watcher and executor
    ws_sync.stop_background_watcher()
    ws_sync.executor.shutdown(wait=True)
