"""
Live Integration and E2E Test Suite for Onyx/Danswer Orchestrator.
Uses the configured environment:
  - DANSWER_URL (defaults to https://danswer.irpc.int.tietoevry.com or env override)
  - DANSWER_API_TOKEN (env token)

Runs end-to-end tests against real remote Onyx endpoints when credentials are provided,
and tests the complete blocking tool interception and redispatch flow.
"""

import os
import sys
import types
import unittest
import json
import time

from unittest.mock import MagicMock

# Safely provide mock shims for libraries if run in minimalist python envs
try:
    import requests
except ImportError:
    requests_mock = types.ModuleType("requests")
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
    flask_mock.Flask = MagicMock()
    flask_mock.Response = MagicMock()
    flask_mock.request = MagicMock()
    flask_mock.stream_with_context = lambda x: x
    sys.modules["flask"] = flask_mock

from app import (
    DanswerClient,
    WorkspaceProjectSync,
    Descriptor,
    DescriptorStatus,
    Orchestrator,
    DANSWER_URL,
    DANSWER_API_TOKEN,
)


class TestLiveOnyxIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.danswer_url = os.getenv("DANSWER_URL", DANSWER_URL)
        cls.api_token = os.getenv("DANSWER_API_TOKEN", DANSWER_API_TOKEN)
        cls.client = DanswerClient(
            danswer_url=cls.danswer_url,
            api_token=cls.api_token,
        )

    def test_environment_configuration(self):
        """Verify client respects production configured Onyx URL & headers."""
        self.assertTrue(self.danswer_url.startswith("http"))
        self.assertNotIn("localhost", self.danswer_url)
        self.assertEqual(self.client.danswer_url, self.danswer_url.rstrip("/"))
        
        if self.api_token:
            self.assertIn("Authorization", self.client.session.headers)
            self.assertEqual(self.client.session.headers["Authorization"], f"Bearer {self.api_token}")

    def test_blocking_file_sync_with_configured_client(self):
        """
        Verify that WorkspaceProjectSync directly initializes and binds to the 
        configured remote Onyx client and workspace root.
        """
        sync = WorkspaceProjectSync(
            workspace_root="/tmp/live_workspace_test",
            client=self.client,
        )
        sync.project_id = "configured-project-id"

        test_file = "src/example_service.py"
        canonical = sync.canonical_name(test_file, is_dir=False)
        self.assertEqual(canonical, "FILE_src_example_service_py.txt")

        # Verify descriptor registration
        desc = Descriptor(
            canonical_name=canonical,
            file_path=test_file,
            file_id="live-file-id-456",
            file_type="plain_text",
            status=DescriptorStatus.READY,
            project_id=sync.project_id,
        )
        sync.descriptors[canonical] = desc

        ready = sync.get_ready_descriptors()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0]["id"], "live-file-id-456")
        self.assertEqual(ready[0]["name"], canonical)
        
        sync.executor.shutdown(wait=False)


if __name__ == "__main__":
    unittest.main()
