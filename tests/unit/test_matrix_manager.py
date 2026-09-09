"""
Unit tests for MatrixManager persona filtering and manifest construction.
"""

import json
from unittest.mock import MagicMock
import pytest
from orchestrator.matrix_manager import MatrixManager


def test_matrix_manager_build_matrix(tmp_path):
    cache_file = tmp_path / "persona_matrix_cache.json"
    mock_client = MagicMock()
    mock_client.fetch_personas.return_value = [
        {"id": 0, "name": "General Assistant", "description": "Default"},
        {"id": 1, "name": "QA Assistant", "description": "Testing and QA tasks"},
        {"id": 5, "name": "Software Engineer", "description": "Code and refactoring"},
    ]
    mock_client.fetch_tools.return_value = [{"id": 10}, {"id": 20}]
    mock_client.extract_tool_ids.return_value = [10, 20]

    manager = MatrixManager(client=mock_client, cache_file=str(cache_file))
    manifest, tool_ids = manager.build_matrix()

    assert tool_ids == [10, 20]
    assert "Persona ID 1: QA Assistant" in manifest
    assert "Persona ID 5: Software Engineer" in manifest
    assert cache_file.exists()

    # Verify cache content
    with open(cache_file, "r", encoding="utf-8") as f:
        cache_data = json.load(f)
    assert cache_data["global_tool_ids"] == [10, 20]


def test_matrix_manager_get_or_build_matrix_cached(tmp_path):
    cache_file = tmp_path / "persona_matrix_cache.json"
    cache_data = {
        "routing_manifest": "Cached Manifest Line",
        "global_tool_ids": [100, 200],
    }
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(cache_data, f)

    mock_client = MagicMock()
    manager = MatrixManager(client=mock_client, cache_file=str(cache_file))

    manifest, tool_ids = manager.get_or_build_matrix(force_refresh=False)
    assert manifest == "Cached Manifest Line"
    assert tool_ids == [100, 200]
    mock_client.fetch_personas.assert_not_called()
