"""
Unit tests for --folder option, top working folder monitoring, file looking, and file writes.
"""

import argparse
import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app import (
    DanswerClient,
    DescriptorStatus,
    WorkspaceProjectSync,
    main as app_main,
)


class TestFolderOptionAndWorkspaceWrites(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="onyx_test_folder_")
        self.mock_client = MagicMock(spec=DanswerClient)
        self.mock_client.danswer_url = "http://mock-onyx:8080"

        # Instantiate WorkspaceProjectSync pointing to temporary target folder
        self.sync = WorkspaceProjectSync(
            workspace_root=self.temp_dir,
            client=self.mock_client,
        )
        self.sync.project_id = "test-proj-folder-opt"

    def tearDown(self):
        self.sync.executor.shutdown(wait=False)
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_cli_folder_argument_parsing(self):
        """Test that app.py main() parses --folder / -f and passes workspace_root to run_server."""
        target_folder = os.path.abspath(self.temp_dir)

        with patch("sys.argv", ["app.py", "--folder", target_folder, "--port", "9090"]):
            with patch("app.run_server") as mock_run_server:
                app_main()
                mock_run_server.assert_called_once_with(port=9090, workspace_root=target_folder)

        with patch("sys.argv", ["app.py", "-f", target_folder]):
            with patch("app.run_server") as mock_run_server:
                app_main()
                mock_run_server.assert_called_once_with(port=8080, workspace_root=target_folder)

    def test_workspace_monitoring_uses_target_folder(self):
        """Test that WorkspaceProjectSync monitors and references the target folder, not current app directory."""
        # Create sample structure in target folder
        sub_dir = os.path.join(self.temp_dir, "src", "module")
        os.makedirs(sub_dir, exist_ok=True)
        file1 = os.path.join(sub_dir, "core.py")
        with open(file1, "w", encoding="utf-8") as f:
            f.write("def compute(): return 42\n")

        # Check tree map generation
        tree_map = self.sync.generate_tree_map()
        self.assertIn(f"PROJECT ROOT DIRECTORY: {os.path.abspath(self.temp_dir)}", tree_map)
        self.assertIn("src/module/core.py", tree_map)

        # Pre-seed a ready descriptor
        canonical = self.sync.canonical_name(file1, is_dir=False)
        self.sync.descriptors[canonical] = MagicMock(
            status=DescriptorStatus.READY,
            file_id="fid-123",
        )

        header = self.sync.get_system_context_header()
        self.assertIn(f"LOCAL WORKSPACE PATH: {os.path.abspath(self.temp_dir)}", header)

    def test_execute_local_tool_writes_file_in_target_folder(self):
        """Test executing write_file local tool writes file in target top folder and syncs descriptor."""
        relative_file = "docs/guide.md"
        file_content = "# User Guide\nThis is a test guide written by local tool."

        res = self.sync.execute_local_non_read_tool(
            "write_file",
            {"file_path": relative_file, "content": file_content},
        )

        self.assertIn("Successfully wrote", res)
        self.assertIn(relative_file, res)

        expected_file_path = os.path.join(self.temp_dir, "docs", "guide.md")
        self.assertTrue(os.path.exists(expected_file_path))
        with open(expected_file_path, "r", encoding="utf-8") as f:
            written_data = f.read()
        self.assertEqual(written_data, file_content)

        # Check that file was registered in descriptors for sync
        canonical = self.sync.canonical_name(expected_file_path, is_dir=False)
        self.assertIn(canonical, self.sync.descriptors)

    def test_execute_local_tool_replace_in_file(self):
        """Test executing replace_in_file edits existing file in target top folder."""
        relative_file = "config.py"
        initial_content = "DB_PORT = 5432\nDEBUG = True\n"
        self.sync.write_workspace_file(relative_file, initial_content)

        res = self.sync.execute_local_non_read_tool(
            "replace_in_file",
            {
                "file_path": relative_file,
                "old_str": "DEBUG = True",
                "new_str": "DEBUG = False",
            },
        )

        self.assertIn("Successfully wrote", res)
        expected_file_path = os.path.join(self.temp_dir, "config.py")
        with open(expected_file_path, "r", encoding="utf-8") as f:
            updated_data = f.read()
        self.assertEqual(updated_data, "DB_PORT = 5432\nDEBUG = False\n")

    def test_execute_local_tool_read_listing_and_find(self):
        """Test directory listing, grep search, and find_files in target top folder."""
        # Setup files
        self.sync.write_workspace_file("src/app.py", "print('Hello World')\n")
        self.sync.write_workspace_file("src/utils.py", "# Helper utils\n")

        # Test list_dir
        ls_res = self.sync.execute_local_non_read_tool("list_dir", {"path": "src"})
        self.assertIn("Directory listing of 'src':", ls_res)
        self.assertIn("app.py", ls_res)
        self.assertIn("utils.py", ls_res)

        # Test grep_search
        grep_res = self.sync.execute_local_non_read_tool("grep_search", {"query": "Hello", "path": "src"})
        self.assertIn("Found 1 matches for 'Hello':", grep_res)
        self.assertIn("src/app.py:1: print('Hello World')", grep_res)

        # Test find_files
        find_res = self.sync.execute_local_non_read_tool("find_files", {"pattern": "utils"})
        self.assertIn("Found 1 matching files for 'utils':", find_res)
        self.assertIn("src/utils.py", find_res)


if __name__ == "__main__":
    unittest.main()
