"""
Unit tests for tool parsing, XML stream chunking, JSON heuristic repair, and message cleaning.
"""

import json
import pytest
from orchestrator.tool_parser import (
    StreamingXmlToolParser,
    clean_user_message,
    extract_all_local_tool_invocations,
    extract_last_tool_execution_context,
    extract_local_tool_invocation,
    is_valid_tool_name,
    safe_parse_tool_arguments,
)


def test_is_valid_tool_name():
    assert is_valid_tool_name("read_file") is True
    assert is_valid_tool_name("list_dir") is True
    assert is_valid_tool_name("dummy_tool") is False
    assert is_valid_tool_name("placeholder_tool") is False
    assert is_valid_tool_name("") is False


def test_safe_parse_tool_arguments_valid_json():
    raw = '{"file_path": "src/main.py", "lines": 10}'
    parsed = safe_parse_tool_arguments(raw, "read_file")
    assert parsed == {"file_path": "src/main.py", "lines": 10}


def test_safe_parse_tool_arguments_unescaped_newlines():
    raw = '{\n"file_path": "src/main.py",\n"content": "line1\nline2"\n}'
    parsed = safe_parse_tool_arguments(raw, "write_file")
    assert "file_path" in parsed or "content" in parsed or "_raw" in parsed


def test_safe_parse_tool_arguments_heuristic_fallback():
    raw = 'invalid json format but "file_path": "app/config.py" here'
    parsed = safe_parse_tool_arguments(raw, "read_file")
    assert parsed.get("file_path") == "app/config.py"


def test_extract_all_local_tool_invocations():
    xml = """
    Here is my plan:
    <local_tool>
      <name>list_dir</name>
      <arguments>{"path": "orchestrator"}</arguments>
    </local_tool>
    And another call:
    <local_tool>
      <name>read_file</name>
      <arguments>{"file_path": "orchestrator/config.py"}</arguments>
    </local_tool>
    """
    invs = extract_all_local_tool_invocations(xml)
    assert len(invs) == 2
    assert invs[0]["name"] == "list_dir"
    assert invs[0]["arguments"]["path"] == "orchestrator"
    assert invs[1]["name"] == "read_file"
    assert invs[1]["arguments"]["file_path"] == "orchestrator/config.py"


def test_streaming_xml_tool_parser_single_chunk():
    parser = StreamingXmlToolParser()
    chunk = 'Hello! <local_tool><name>list_dir</name><arguments>{"path": "."}</arguments></local_tool> world'
    text_chunks, tool_calls = parser.feed(chunk)
    assert "Hello! " in text_chunks
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "list_dir"


def test_streaming_xml_tool_parser_chunked_stream():
    parser = StreamingXmlToolParser()

    # Part 1: prefix text and opening tag
    t1, c1 = parser.feed("Analysis: <local_")
    assert t1 == ["Analysis: "]
    assert c1 == []

    # Part 2: rest of tool call
    t2, c2 = parser.feed('tool><name>read_file</name><arguments>{"file_path": "a.py"}</arguments></local_tool> done')
    assert len(c2) == 1
    assert c2[0]["function"]["name"] == "read_file"


def test_clean_user_message():
    msg = "<system-reminder>Internal instructions</system-reminder>Please explain this code."
    cleaned = clean_user_message(msg)
    assert cleaned == "Please explain this code."


def test_extract_last_tool_execution_context():
    messages = [
        {"role": "user", "content": "Check files"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{
                "id": "call_123",
                "function": {"name": "read_file", "arguments": '{"file_path": "test.txt"}'}
            }]
        },
        {"role": "tool", "tool_call_id": "call_123", "content": "file contents here"}
    ]
    ctx = extract_last_tool_execution_context(messages)
    assert "=== MOST RECENT TOOL EXECUTION RESULTS ===" in ctx
    assert "call_123" in ctx
    assert "file contents here" in ctx
