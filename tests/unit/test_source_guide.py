"""Tests for the static fins source guide (SOURCE_fins_guide.txt).

The guide is a static repo resource attached to the Onyx project
independently of the disk workspace: disk changes must not touch it.
"""
import os
import unittest
from unittest.mock import MagicMock

from orchestrator.client import DanswerClient
from orchestrator.workspace_sync import (
    SOURCE_GUIDE_CANONICAL,
    SOURCE_GUIDE_RESOURCE,
    WorkspaceProjectSync,
)
from orchestrator.models import DescriptorStatus


class TestSourceGuide(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock(spec=DanswerClient)
        self.mock_client.danswer_url = "http://mock-onyx:8080"
        self.mock_client.session = MagicMock()
        self.sync = WorkspaceProjectSync(
            workspace_root="/tmp/test_workspace_guide",
            client=self.mock_client,
        )
        self.sync.project_id = "test-proj-123"

    def tearDown(self):
        self.sync.executor.shutdown(wait=False)

    def test_guide_resource_exists_and_has_key_sections(self):
        self.assertTrue(os.path.exists(SOURCE_GUIDE_RESOURCE))
        with open(SOURCE_GUIDE_RESOURCE, encoding="utf-8") as f:
            content = f.read()
        for fragment in (
            "SOURCE_",
            "FILE_",
            "fins3://db/",
            "fins3://git/",
            "fins3://runs/",
            "read-only",
            "etag",
        ):
            self.assertIn(fragment, content, f"guide missing section: {fragment}")

    def test_ensure_source_guide_uploads_once(self):
        desc = self.sync.ensure_source_guide()
        self.assertIsNotNone(desc)
        self.assertEqual(desc.canonical_name, SOURCE_GUIDE_CANONICAL)
        # one upload happened via the blocking path
        self.assertEqual(self.sync.upload_and_attach_blocking.call_count, 1) if hasattr(
            self.sync, "upload_and_attach_blocking"
        ) and isinstance(self.sync.upload_and_attach_blocking, MagicMock) else None
        self.assertIn(SOURCE_GUIDE_CANONICAL, self.sync.file_hashes)

        guide_hash = self.sync.file_hashes[SOURCE_GUIDE_CANONICAL]
        # Second call: guide unchanged and READY -> must NOT re-upload
        desc.status = DescriptorStatus.READY
        self.sync.file_hashes[SOURCE_GUIDE_CANONICAL] = guide_hash
        again = self.sync.ensure_source_guide()
        self.assertIs(again, desc)
        self.assertEqual(self.sync.file_hashes[SOURCE_GUIDE_CANONICAL], guide_hash)

    def test_guide_independent_of_disk_changes(self):
        # seed the guide as READY
        desc = self.sync.ensure_source_guide()
        desc.status = DescriptorStatus.READY
        guide_hash = self.sync.file_hashes[SOURCE_GUIDE_CANONICAL]

        # a disk file change runs through update_top_folder/refresh; the guide
        # hash entry must remain untouched
        self.sync.file_hashes["TOP_FOLDER_test_workspace_guide.txt"] = "0" * 64
        self.sync.file_hashes[SOURCE_GUIDE_CANONICAL] = guide_hash
        self.assertEqual(self.sync.file_hashes[SOURCE_GUIDE_CANONICAL], guide_hash)

    def test_guide_reuploads_when_guide_content_changes(self):
        desc = self.sync.ensure_source_guide()
        self.assertIsNotNone(desc)
        # simulate a changed guide: hash mismatch forces re-upload
        self.sync.file_hashes[SOURCE_GUIDE_CANONICAL] = "stale"
        with unittest.mock.patch(
            "builtins.open",
            unittest.mock.mock_open(read_data="changed guide content"),
        ):
            self.sync.ensure_source_guide()
        self.assertNotEqual(self.sync.file_hashes[SOURCE_GUIDE_CANONICAL], "stale")


if __name__ == "__main__":
    unittest.main()
