"""
Unit and integration tests for Synchronous Blocking File Upload & Contextual Redispatch (Loopback Grounding).
Verifies:
1. upload_and_attach_blocking() creates READY descriptors synchronously.
2. Tool read calls are intercepted from the model output stream.
3. The query is automatically redispatched to Onyx with file descriptors attached.
4. The persona is optionally re-evaluated and reassigned based on the newly indexed file context.
"""

import unittest
import os
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
)


class TestBlockingFileSyncAndRedispatch(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=DanswerClient)
        self.mock_client.danswer_url = "http://mock-onyx:8080"
        self.mock_client.session = MagicMock()

        self.sync = WorkspaceProjectSync(
            workspace_root="/tmp/test_workspace",
            client=self.mock_client,
        )
        self.sync.project_id = "proj-redispatch-test"

    def tearDown(self):
        self.sync.executor.shutdown(wait=False)

    def test_upload_and_attach_blocking_direct(self):
        """
        Verify that upload_and_attach_blocking completes upload + attach synchronously,
        returning a Descriptor with status READY.
        """
        file_path = "src/security/crypto.py"
        content = "def verify_hmac(key, msg, sig): return True"
        canonical = self.sync.canonical_name(file_path, is_dir=False)

        self.mock_client.upload_project_file.return_value = {
            "id": "onyx-crypto-uuid-123",
            "file_type": "plain_text",
            "name": canonical,
        }
        self.mock_client.attach_file_to_project.return_value = True

        desc = self.sync.upload_and_attach_blocking(
            file_path=file_path,
            content=content,
        )

        self.assertIsNotNone(desc)
        self.assertEqual(desc.status, DescriptorStatus.READY)
        self.assertEqual(desc.file_id, "onyx-crypto-uuid-123")
        self.assertEqual(desc.canonical_name, canonical)

        # Check it is in ready descriptors
        ready_descriptors = self.sync.get_ready_descriptors()
        self.assertEqual(len(ready_descriptors), 1)
        self.assertEqual(ready_descriptors[0]["id"], "onyx-crypto-uuid-123")

    def test_intercept_tool_call_and_redispatch_flow(self):
        """
        Simulate LLM emitting <local_tool><name>read_file</name>...
        Verify that Orchestrator intercepts the tool call, blocks for upload,
        reassigns persona if appropriate, and redispatches query with file attached.
        """
        file_path = "src/security/crypto.py"
        canonical = self.sync.canonical_name(file_path, is_dir=False)

        # Mock blocking upload response
        self.mock_client.upload_project_file.return_value = {
            "id": "onyx-crypto-uuid-123",
            "file_type": "plain_text",
            "name": canonical,
        }
        self.mock_client.attach_file_to_project.return_value = True

        orchestrator = Orchestrator(
            client=self.mock_client,
            routing_manifest="Test manifest",
            tool_ids=[1, 2],
            workspace_sync=self.sync,
        )

        # Mock initial segment
        mock_segment = MagicMock()
        mock_segment.session_id = "session-initial-001"
        mock_segment.persona_id = 0
        mock_segment.inherited_context = ""
        orchestrator.get_or_create_initial_segment = MagicMock(return_value=mock_segment)

        # Persona detection remains stable
        orchestrator.detect_mode = MagicMock(return_value=("CONTINUE", 0, "same persona active"))

        # Mock the two calls to iter_stream_text:
        # Call 1: Emits the <local_tool> invocation
        # Call 2: Emits the grounded, synthesized final answer
        tool_call_xml = (
            '<local_tool>'
            '<name>read_file</name>'
            '<arguments>{"file_path": "src/security/crypto.py"}</arguments>'
            '</local_tool>'
        )
        grounded_answer = "The crypto module implements secure HMAC verification without timing attacks."

        self.mock_client.iter_stream_text = MagicMock(side_effect=[
            iter([tool_call_xml]),
            iter([grounded_answer]),
        ])

        # Pre-seed workspace sync with custom content resolver for test
        with patch.object(self.sync, "upload_and_attach_blocking") as mock_blocking_sync:
            ready_desc = Descriptor(
                canonical_name=canonical,
                file_path=file_path,
                file_id="onyx-crypto-uuid-123",
                file_type="plain_text",
                status=DescriptorStatus.READY,
                project_id="proj-redispatch-test",
            )
            self.sync.descriptors[canonical] = ready_desc
            mock_blocking_sync.return_value = ready_desc

            # Process query
            messages = [{"role": "user", "content": "Please review the security of crypto.py"}]
            chunks = list(orchestrator.process_query(
                conversation_id="conv-redispatch-1",
                messages=messages,
            ))

            # Verify blocking sync was called
            mock_blocking_sync.assert_called_once_with("src/security/crypto.py")

            # Verify send_message was called twice (turn 1 + redispatch turn 2)
            self.assertEqual(self.mock_client.send_message.call_count, 2)

            # Turn 2 call kwargs must contain the grounded file_descriptor, prompt prefix, and active session
            turn2_kwargs = self.mock_client.send_message.call_args_list[1][1]
            self.assertEqual(turn2_kwargs["session_id"], "session-initial-001")
            self.assertIn("file_descriptors", turn2_kwargs)
            self.assertEqual(len(turn2_kwargs["file_descriptors"]), 1)
            self.assertEqual(turn2_kwargs["file_descriptors"][0]["id"], "onyx-crypto-uuid-123")
            self.assertIn("FILE src/security/crypto.py was attached as FILE_src_security_crypto_py.txt", turn2_kwargs["message"])

            # Output should contain the grounded answer seamlessly without persona switch interruptions
            full_output = "".join(chunks)
            self.assertIn(grounded_answer, full_output)

    def test_multi_tool_batch_intercept_and_redispatch(self):
        """
        Verify that when an LLM emits a batch of tools (e.g. list_dir + read_file),
        the non-read tool is executed locally, the read tool is synced blocking to Onyx,
        and both results are synthesized into the redispatched prompt.
        """
        orchestrator = Orchestrator(
            client=self.mock_client,
            routing_manifest="Mock routing manifest",
            tool_ids=[1, 2],
            workspace_sync=self.sync,
        )

        mock_segment = MagicMock()
        mock_segment.session_id = "session-batch-001"
        mock_segment.persona_id = 0
        mock_segment.inherited_context = ""
        orchestrator.get_or_create_initial_segment = MagicMock(return_value=mock_segment)
        orchestrator.detect_mode = MagicMock(return_value=("CONTINUE", 0, "active"))

        # Model emits 2 tools: list_dir then read_file
        multi_tool_xml = (
            '<local_tool>\n'
            '<name>list_dir</name>\n'
            '<arguments>{"path": "src/security"}</arguments>\n'
            '</local_tool>\n'
            '<local_tool>\n'
            '<name>read_file</name>\n'
            '<arguments>{"file_path": "src/security/crypto.py"}</arguments>\n'
            '</local_tool>'
        )
        final_answer = "Found 2 files in security directory. Audited crypto.py successfully."

        self.mock_client.iter_stream_text = MagicMock(side_effect=[
            iter([multi_tool_xml]),
            iter([final_answer]),
        ])

        # Create dummy directory and file on test workspace disk
        sec_dir = os.path.join(self.sync.root, "src", "security")
        os.makedirs(sec_dir, exist_ok=True)
        with open(os.path.join(sec_dir, "crypto.py"), "w") as f:
            f.write("# crypto file")
        with open(os.path.join(sec_dir, "tokens.py"), "w") as f:
            f.write("# tokens file")

        canonical = self.sync.canonical_name("src/security/crypto.py", is_dir=False)
        ready_desc = Descriptor(
            canonical_name=canonical,
            file_path="src/security/crypto.py",
            file_id="onyx-crypto-batch-999",
            file_type="plain_text",
            status=DescriptorStatus.READY,
            project_id="proj-redispatch-test",
        )
        self.sync.descriptors[canonical] = ready_desc

        with patch.object(self.sync, "upload_and_attach_blocking", return_value=ready_desc) as mock_sync:
            messages = [{"role": "user", "content": "List the security folder and audit crypto.py"}]
            chunks = list(orchestrator.process_query(
                conversation_id="conv-batch-1",
                messages=messages,
            ))

            # Verify read_file was synced blocking
            mock_sync.assert_called_once_with("src/security/crypto.py")

            # Verify turn 2 was dispatched with tool results and attachment notification
            self.assertEqual(self.mock_client.send_message.call_count, 2)
            turn2_kwargs = self.mock_client.send_message.call_args_list[1][1]
            redispatched_message = turn2_kwargs["message"]

            self.assertIn("FILE src/security/crypto.py was attached as FILE_src_security_crypto_py.txt", redispatched_message)
            self.assertIn("[LOCAL TOOL EXECUTION RESULTS]:", redispatched_message)
            self.assertIn("Directory listing of 'src/security':", redispatched_message)
            self.assertIn("crypto.py", redispatched_message)
            self.assertIn("tokens.py", redispatched_message)
            self.assertIn("Attached and indexed in project context as FILE_src_security_crypto_py.txt", redispatched_message)

            full_output = "".join(chunks)
            self.assertIn(final_answer, full_output)


if __name__ == "__main__":
    unittest.main()
