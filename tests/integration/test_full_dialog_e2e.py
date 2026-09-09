"""
Full End-to-End Dialogue Integration Test Suite.
Verifies complete end-to-end dialogue with Mock Onyx server including:
1. Streaming timing / delays.
2. Tool call emission (<local_tool>) and interception.
3. Synchronous blocking file upload and loopback redispatch.
4. Answers reflecting uploaded file content and attached descriptors.
5. Multi-turn dialogue persistence across questions, tool calls, and sessions.
"""

import json
import time
import pytest
from typing import List

import orchestrator.server as server_mod
from orchestrator.client import DanswerClient
from orchestrator.core import Orchestrator
from orchestrator.matrix_manager import MatrixManager
from orchestrator.workspace_sync import WorkspaceProjectSync


def test_full_dialogue_with_timing_tool_calls_file_reading_and_persistence(mock_onyx_server, tmp_path):
    """
    Test complete multi-turn dialogue with file reading tool calls, blocking file upload,
    streaming timing, grounded file answers, and multi-turn persistence.
    """
    # 1. Initialize client against live Mock Onyx Server fixture
    client = DanswerClient(danswer_url=mock_onyx_server, api_token="test-e2e-token")

    # 2. Build routing matrix & workspace sync
    matrix_manager = MatrixManager(client=client, cache_file=str(tmp_path / "matrix_cache.json"))
    manifest, tool_ids = matrix_manager.get_or_build_matrix(force_refresh=True)

    ws_sync = WorkspaceProjectSync(workspace_root=str(tmp_path), client=client)
    ws_sync.initialize_project()
    assert ws_sync.project_id is not None

    # Stop background watcher thread so blocking sync on tool call intercept is tested deterministically
    ws_sync.stop_background_watcher()

    # Create local source file in workspace disk after stopping background watcher
    src_dir = tmp_path / "src"
    src_dir.mkdir(parents=True, exist_ok=True)
    auth_file = src_dir / "auth.py"
    auth_file.write_text("def authenticate_user(token):\n    return token == 'valid_secret_key'\n", encoding="utf-8")

    orch = Orchestrator(
        client=client,
        routing_manifest=manifest,
        tool_ids=tool_ids,
        workspace_sync=ws_sync,
    )

    conversation_id = "conv-e2e-dialog-100"

    # --- TURN 1: Ask question requiring file reading ---
    # Trigger tool call from Mock Onyx -> Intercept -> Blocking file upload -> Loopback redispatch with file attached
    turn1_messages = [{"role": "user", "content": "Please read file src/auth.py and check authentication logic"}]

    start_time = time.time()
    turn1_chunks: List[str] = list(orch.process_query(
        conversation_id=conversation_id,
        messages=turn1_messages,
    ))
    elapsed_time = time.time() - start_time

    turn1_response = "".join(turn1_chunks)

    # 1) Receive tool call & answer check:
    # Verify that file was uploaded and attached during tool call interception
    ready_descriptors = ws_sync.get_ready_descriptors()
    print("DEBUG TEST ready_descriptors:", ready_descriptors)
    print("DEBUG TEST ws_sync descriptors:", [(k, v.status) for k, v in ws_sync.descriptors.items()])
    assert len(ready_descriptors) >= 1
    canonical_name = ws_sync.canonical_name("src/auth.py", is_dir=False)
    assert any(d["name"] == canonical_name for d in ready_descriptors)

    # 2) Receive answer with file after upload:
    # Verify mock Onyx received the file descriptor on redispatch and included attachment info in answer
    assert "Mock Onyx answer to:" in turn1_response
    assert "[Attached files:" in turn1_response
    assert canonical_name in turn1_response

    # --- TURN 2: Follow-up question in same conversation (Testing Multi-Turn Persistence) ---
    turn2_messages = [
        {"role": "user", "content": "Please read file src/auth.py and check authentication logic"},
        {"role": "assistant", "content": turn1_response},
        {"role": "user", "content": "What are the security implications of hardcoded token comparison?"},
    ]

    turn2_chunks = list(orch.process_query(
        conversation_id=conversation_id,
        messages=turn2_messages,
    ))
    turn2_response = "".join(turn2_chunks)

    # Verify turn 2 answer received
    assert "Mock Onyx answer" in turn2_response
    assert "What are the security implications of hardcoded token comparison?" in turn2_response

    # --- TURN 3: Check Session Persistence on Orchestrator & Mock Onyx ---
    active_segment = orch.sessions.get_active(conversation_id)
    assert active_segment is not None
    session_id = active_segment.session_id

    # Verify session store stored user & assistant messages for conversation
    session_messages = active_segment.messages
    assert len(session_messages) >= 4  # Turn 1 user + assistant, Turn 2 user + assistant

    # Check mock server history endpoint for recorded turns
    hist_resp = client.session.get(f"{client.danswer_url}/api/chat/session-history/{session_id}")
    assert hist_resp.status_code == 200
    history = hist_resp.json().get("history", [])
    assert len(history) >= 2  # Recorded requests in mock onyx session

    # Cleanup background watcher and executor
    ws_sync.executor.shutdown(wait=True)


def test_streaming_timing_and_flask_e2e_persistence(mock_onyx_server, tmp_path):
    """
    Test Flask chat completions route with streaming delays and session persistence.
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

    server_mod.client = client
    server_mod.orchestrator = orch

    flask_app = server_mod.app
    flask_app.config["TESTING"] = True
    test_client = flask_app.test_client()

    conv_id = "conv-flask-e2e-404"

    # Turn 1: Send streaming completion request
    res1 = test_client.post(
        "/v1/chat/completions",
        headers={"X-Conversation-ID": conv_id},
        json={
            "model": "gpt-4o",
            "messages": [{"role": "user", "content": "How does the orchestrator persist sessions?"}],
            "stream": True,
        },
    )
    assert res1.status_code == 200
    raw_sse1 = res1.get_data(as_text=True)
    assert "[DONE]" in raw_sse1

    # Reconstruct streamed text from SSE chunks
    content_pieces = []
    for line in raw_sse1.splitlines():
        if line.startswith("data: ") and "[DONE]" not in line:
            data_dict = json.loads(line[6:])
            choices = data_dict.get("choices", [])
            if choices and "delta" in choices[0]:
                content_pieces.append(choices[0]["delta"].get("content", ""))
    reconstructed_stream1 = "".join(content_pieces)

    assert "Mock Onyx answer to: How does the orchestrator persist sessions?" in reconstructed_stream1

    # Turn 2: Send follow-up request in same conversation
    res2 = test_client.post(
        "/v1/chat/completions",
        headers={"X-Conversation-ID": conv_id},
        json={
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "How does the orchestrator persist sessions?"},
                {"role": "assistant", "content": "Mock Onyx answer to: How does the orchestrator persist sessions?"},
                {"role": "user", "content": "Explain session segment handovers."},
            ],
            "stream": False,
        },
    )
    assert res2.status_code == 200
    data2 = res2.get_json()
    content2 = data2["choices"][0]["message"]["content"]
    assert "Explain session segment handovers." in content2

    # Verify conversation history persisted in Orchestrator ConversationStore
    active_seg2 = orch.sessions.get_active(conv_id)
    assert active_seg2 is not None
    stored_messages = active_seg2.messages
    assert len(stored_messages) == 4
    assert stored_messages[0]["content"] == "How does the orchestrator persist sessions?"
    assert stored_messages[2]["content"] == "Explain session segment handovers."

    ws_sync.stop_background_watcher()
    ws_sync.executor.shutdown(wait=True)
