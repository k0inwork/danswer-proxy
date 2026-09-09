"""
Unit tests for domain models, Descriptor, Segment, and SessionRegistry.
"""

import pytest
from orchestrator.models import Descriptor, DescriptorStatus, Segment, SessionRegistry


def test_descriptor_status_enum():
    assert DescriptorStatus.PENDING_UPLOAD.value == "pending_upload"
    assert DescriptorStatus.UPLOADED.value == "uploaded"
    assert DescriptorStatus.READY.value == "ready"
    assert DescriptorStatus.FAILED.value == "failed"


def test_descriptor_to_onyx_dict():
    desc = Descriptor(
        canonical_name="FILE_app_py.txt",
        file_path="/app/app.py",
        file_id="file-uuid-123",
        file_type="plain_text",
        status=DescriptorStatus.READY,
        project_id="proj-123",
    )
    assert desc.canonical_name == "FILE_app_py.txt"
    assert desc.file_id == "file-uuid-123"
    assert desc.status == DescriptorStatus.READY

    onyx_dict = desc.to_onyx_dict()
    assert onyx_dict == {
        "id": "file-uuid-123",
        "type": "plain_text",
        "name": "FILE_app_py.txt",
    }


def test_session_registry():
    registry = SessionRegistry()
    assert registry.count() == 0
    assert registry.get_all() == []

    registry.register("sess-1", "test")
    registry.register("sess-2", "test")
    assert registry.count() == 2
    assert set(registry.get_all()) == {"sess-1", "sess-2"}

    registry.unregister("sess-1", "test")
    assert registry.count() == 1
    assert registry.get_all() == ["sess-2"]


def test_segment():
    seg = Segment(
        segment_id=1,
        persona_id=5,
        session_id="sess-xyz",
        inherited_context="Previous summary",
    )
    assert seg.segment_id == 1
    assert seg.persona_id == 5
    assert seg.session_id == "sess-xyz"
    assert seg.inherited_context == "Previous summary"
    assert seg.status == "ACTIVE"
    assert seg.compaction is None
    assert seg.messages == []
