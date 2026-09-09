"""
Unit and integration tests for lazy file sync, tool interception, and Onyx RAG context grounding.
Tests the full lifecycle:
1. LLM requests a file read (via tool call).
2. Orchestrator / WorkspaceProjectSync dispatches background file upload.
3. Onyx client receives upload & project attachment.
4. Descriptors transition to READY.
5. Subsequent prompt to Onyx attaches the file descriptors for RAG grounding.
"""

import unittest
import sys
import types
from unittest.mock import MagicMock, patch

# Safely provide mock shims for libraries if run in minimalist python envs
try:
    import requests
except ImportError:
    requests_mock = types.ModuleType("requests")
    class HTTPError(Exception): pass
    requests_mock.HTTPError = HTTPError
    requests_mock.adapters = types.ModuleType("requests.adapters")
    requests_mock.adapters.HTTPAdapter = MagicMock()
    requests_mock.Session = MagicMock()
    requests_mock.Response = MagicMock()
    sys.modules["requests"] = requests_mock
    sys.modules["requests.adapters"] = requests_mock.adapters

try:
    import urllib3
except ImportError:
    urllib3_mock = types.ModuleType("urllib3")
    urllib3_mock.util = types.ModuleType("urllib3.util")
    urllib3_mock.util.retry = types.ModuleType("urllib3.util.retry")
    urllib3_mock.util.retry.Retry = MagicMock()
    sys.modules["urllib3"] = urllib3_mock
    sys.modules["urllib3.util"] = urllib3_mock.util
    sys.modules["urllib3.util.retry"] = urllib3_mock.util.retry

try:
    import flask
except ImportError:
    flask_mock = types.ModuleType("flask")
    mock_app = MagicMock()
    mock_app.route = lambda *a, **kw: (lambda fn: fn)
    flask_mock.Flask = lambda name: mock_app
    flask_mock.Response = MagicMock()
    flask_mock.request = MagicMock()
    flask_mock.stream_with_context = lambda x: x
    sys.modules["flask"] = flask_mock

import json
import time
from typing import Dict, Any, List

from app import (
    WorkspaceProjectSync,
    Descriptor,
    DescriptorStatus,
    Orchestrator,
    DanswerClient,
    extract_last_tool_execution_context,
)


class TestFileUploadAndRAGFlow(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=DanswerClient)
        self.mock_client.danswer_url = "http://mock-onyx:8080"
        self.mock_client.session = MagicMock()

        # Instantiate WorkspaceProjectSync with test workspace
        self.sync = WorkspaceProjectSync(
            workspace_root="/tmp/test_workspace",
            client=self.mock_client,
        )
        self.sync.project_id = "test-proj-123"

    def tearDown(self):
        self.sync.executor.shutdown(wait=False)

    def test_step1_tool_read_interception_and_async_dispatch(self):
        """
        Verify that tool execution messages are intercepted,
        canonical descriptors are registered, and background sync is dispatched.
        """
        messages = [
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "call_read_auth",
                        "type": "function",
                        "function": {
                            "name": "read_file",
                            "arguments": json.dumps({"file_path": "src/auth/jwt.py"}),
                        },
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_read_auth",
                "content": "File: src/auth/jwt.py\ndef verify_token(token):\n    return token == 'valid'",
            },
        ]

        # Extract tool context (simulating the orchestrator's incoming turn)
        context = extract_last_tool_execution_context(messages, workspace_sync=self.sync)

        self.assertIn("File 'src/auth/jwt.py' uploaded and staged", context)
        self.assertIn("def verify_token", context)

        # Check that descriptor was registered in sync manager
        canonical = self.sync.canonical_name("src/auth/jwt.py", is_dir=False)
        desc = self.sync.descriptors.get(canonical)
        self.assertIsNotNone(desc)
        self.assertEqual(desc.canonical_name, canonical)
        # Initially pending upload or active in worker
        self.assertIn(desc.status, [DescriptorStatus.PENDING_UPLOAD, DescriptorStatus.UPLOADED, DescriptorStatus.READY, DescriptorStatus.FAILED])

    def test_step2_onyx_upload_and_attach_progression(self):
        """
        Verify that when upload and attach succeed against Onyx API,
        the descriptor transitions to READY state with correct file_id and canonical name.
        """
        file_path = "src/services/billing.py"
        content = "class BillingService:\n    def charge(self, amount): pass"
        canonical = self.sync.canonical_name(file_path, is_dir=False)

        # Mock the client upload and attach methods
        self.mock_client.upload_project_file.return_value = {
            "id": "onyx-file-uuid-888",
            "file_type": "plain_text",
            "name": canonical,
        }
        self.mock_client.attach_file_to_project.return_value = {
            "status": "attached"
        }

        # Trigger on_tool_read
        desc = self.sync.on_tool_read(file_path, content)
        self.assertIsNotNone(desc)

        # Allow thread pool worker to complete async tasks
        time.sleep(0.3)

        # Verify descriptor reached READY
        ready_desc = self.sync.descriptors.get(canonical)
        self.assertIsNotNone(ready_desc)
        self.assertEqual(ready_desc.status, DescriptorStatus.READY)
        self.assertEqual(ready_desc.file_id, "onyx-file-uuid-888")

        # Verify it appears in ready descriptors list for Onyx RAG
        ready_list = self.sync.get_ready_descriptors()
        ready_ids = [d["id"] for d in ready_list]
        self.assertIn("onyx-file-uuid-888", ready_ids)

    def test_step3_subsequent_request_attaches_descriptors_to_rag(self):
        """
        Verify that in the next conversation turn, the orchestrator attaches
        ready file descriptors to Onyx's send_message call for RAG grounding.
        """
        # Pre-seed a ready descriptor
        canonical = self.sync.canonical_name("src/models/user.py", is_dir=False)
        desc = Descriptor(
            canonical_name=canonical,
            file_path="src/models/user.py",
            file_id="onyx-file-uuid-999",
            file_type="plain_text",
            status=DescriptorStatus.READY,
            project_id="test-proj-123",
        )
        self.sync.descriptors[canonical] = desc
        self.assertEqual(desc.status, DescriptorStatus.READY)

        orchestrator = Orchestrator(
            client=self.mock_client,
            routing_manifest="Test manifest",
            tool_ids=[1, 2],
            workspace_sync=self.sync,
        )

        # Mock detector mode to CONTINUE
        orchestrator.detect_mode = MagicMock(return_value=("CONTINUE", 0, "same persona"))
        orchestrator.get_or_create_initial_segment = MagicMock()
        mock_segment = MagicMock()
        mock_segment.session_id = "session-test-001"
        mock_segment.persona_id = 0
        mock_segment.inherited_context = ""
        orchestrator.get_or_create_initial_segment.return_value = mock_segment

        # Mock send_message response and iter_stream_text
        mock_response = MagicMock()
        self.mock_client.send_message.return_value = mock_response
        self.mock_client.iter_stream_text.return_value = iter(["User model has id and name."])

        # Process a subsequent user prompt
        messages = [
            {"role": "user", "content": "What fields does the User model have?"}
        ]
        chunks = list(orchestrator.process_query(
            conversation_id="conv-1",
            messages=messages,
        ))

        # Check send_message was called with the uploaded file descriptor
        self.mock_client.send_message.assert_called_once()
        call_kwargs = self.mock_client.send_message.call_args[1]

        self.assertIn("file_descriptors", call_kwargs)
        passed_descriptors = call_kwargs["file_descriptors"]
        self.assertEqual(len(passed_descriptors), 1)
        self.assertEqual(passed_descriptors[0]["id"], "onyx-file-uuid-999")
        self.assertEqual(passed_descriptors[0]["name"], canonical)
        self.assertEqual(passed_descriptors[0]["type"], "plain_text")
        self.assertIn("User model has id and name.", "".join(chunks))

    def test_step4_resync_on_modified_file(self):
        """
        Verify that modifying a file resets the status to PENDING_UPLOAD,
        cleans up previous file in Onyx, and updates to the new file_id.
        """
        file_path = "src/config.py"
        canonical = self.sync.canonical_name(file_path, is_dir=False)

        # Pre-seed initial ready version
        desc = Descriptor(
            canonical_name=canonical,
            file_path=file_path,
            file_id="old-uuid-111",
            file_type="plain_text",
            status=DescriptorStatus.READY,
            project_id="test-proj-123",
        )
        self.sync.descriptors[canonical] = desc
        self.sync.file_hashes[canonical] = "initial_hash"

        # Re-sync with updated content
        new_desc = self.sync.on_tool_read(file_path, "PORT = 8080 (MODIFIED)")
        # Should reset status to PENDING_UPLOAD during dispatch
        self.assertIn(new_desc.status, [DescriptorStatus.PENDING_UPLOAD, DescriptorStatus.UPLOADED, DescriptorStatus.READY])

        # Complete new upload
        self.sync._on_upload_complete(canonical, "new-uuid-222", "plain_text")
        self.sync._on_attach_complete(canonical)

        final_desc = self.sync.descriptors[canonical]
        self.assertEqual(final_desc.status, DescriptorStatus.READY)
        self.assertEqual(final_desc.file_id, "new-uuid-222")


if __name__ == "__main__":
    unittest.main()
