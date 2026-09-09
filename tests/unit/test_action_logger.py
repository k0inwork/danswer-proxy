"""
Unit tests for explicit action logging and run logger functionality.
"""

from datetime import datetime
import json
import logging
import os
import shutil
import tempfile
import pytest

from orchestrator.action_logger import (
    ActionLogger,
    get_run_logger,
    init_run_logger,
)


@pytest.fixture
def temp_log_dir():
    temp_dir = tempfile.mkdtemp(prefix="onyx_test_log_")
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


def test_action_logger_directory_structure(temp_log_dir):
    logger_inst = ActionLogger(base_log_dir=temp_log_dir, run_id="test_run_123")

    assert os.path.exists(logger_inst.run_dir)
    assert os.path.exists(logger_inst.actions_log_path)
    assert os.path.exists(logger_inst.run_info_path)

    date_str = datetime.now().strftime("%Y-%m-%d")
    assert date_str in logger_inst.run_dir
    assert "run_test_run_123" in logger_inst.run_dir

    with open(logger_inst.run_info_path, "r", encoding="utf-8") as f:
        run_info = json.load(f)

    assert run_info["run_id"] == "test_run_123"
    assert run_info["date"] == date_str


def test_action_logger_llm_request_response(temp_log_dir):
    logger_inst = ActionLogger(base_log_dir=temp_log_dir, run_id="test_run_llm")

    logger_inst.log_llm_request(
        model="gpt-5.4-nano",
        session_id="session_abc",
        message="Hello world test query",
        temperature=0.3,
        allowed_tools=[1, 2],
    )

    logger_inst.log_llm_response(
        model="gpt-5.4-nano",
        session_id="session_abc",
        response_summary="Hello! How can I help you today?",
        duration_ms=120.5,
    )

    with open(logger_inst.actions_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    assert "[LLM_REQUEST] [SEND]" in log_content
    assert "model=gpt-5.4-nano" in log_content
    assert "session_id=session_abc" in log_content
    assert "message_preview=Hello world test query" in log_content

    assert "[LLM_RESPONSE] [RECEIVED]" in log_content
    assert "response_summary=Hello! How can I help you today?" in log_content
    assert "duration_ms=120.5" in log_content


def test_action_logger_file_operations(temp_log_dir):
    logger_inst = ActionLogger(base_log_dir=temp_log_dir, run_id="test_run_files")

    logger_inst.log_file_upload(
        file_path="src/main.py",
        canonical_name="FILE_src_main_py.txt",
        file_id="fid_999",
        project_id="pid_123",
        status="READY",
    )

    logger_inst.log_file_read(
        file_path="src/main.py",
        canonical_name="FILE_src_main_py.txt",
        size_bytes=1024,
        revision=2,
        source="on_tool_read",
    )

    with open(logger_inst.actions_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    assert "[FILE_UPLOAD] [SYNC]" in log_content
    assert "file_path=src/main.py" in log_content
    assert "file_id=fid_999" in log_content
    assert "status=READY" in log_content

    assert "[FILE_READ] [INSPECT]" in log_content
    assert "canonical_name=FILE_src_main_py.txt" in log_content
    assert "revision=2" in log_content


def test_action_logger_tool_calls(temp_log_dir):
    logger_inst = ActionLogger(base_log_dir=temp_log_dir, run_id="test_run_tools")

    logger_inst.log_tool_call(
        tool_name="list_dir",
        arguments={"path": "."},
        result_summary="Directory listing of '.': app.py, orchestrator/",
        intercepted=False,
    )

    logger_inst.log_tool_call(
        tool_name="read_file",
        arguments={"path": "app.py"},
        result_summary="Intercepted read for blocking sync",
        intercepted=True,
    )

    with open(logger_inst.actions_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    assert "[TOOL_CALL] [EXECUTE]" in log_content
    assert "tool_name=list_dir" in log_content

    assert "[TOOL_CALL] [INTERCEPTED]" in log_content
    assert "tool_name=read_file" in log_content


def test_action_logger_captures_standard_logging(temp_log_dir):
    logger_inst = ActionLogger(base_log_dir=temp_log_dir, run_id="test_run_stdlog")

    app_logger = logging.getLogger("danswer-orchestrator-v4")
    app_logger.info("Test info log message from standard logging module")

    with open(logger_inst.actions_log_path, "r", encoding="utf-8") as f:
        log_content = f.read()

    assert "Test info log message from standard logging module" in log_content


def test_init_run_logger_singleton(temp_log_dir):
    inst1 = init_run_logger(base_log_dir=temp_log_dir, run_id="run_alpha", force_new=True)
    inst2 = get_run_logger()

    assert inst1 is inst2
    assert inst2.run_id == "run_alpha"

    inst3 = init_run_logger(base_log_dir=temp_log_dir, run_id="run_beta", force_new=True)
    assert inst3.run_id == "run_beta"
    assert get_run_logger() is inst3
