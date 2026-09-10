"""
Streaming XML/JSON tool call parser, heuristics repair, and execution context extractors.
"""

import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from orchestrator.config import logger
from orchestrator.models import DescriptorStatus


DUMMY_TOOL_NAMES = {
    "tool_name",
    "actual_tool_name",
    "name_of_tool",
    "placeholder_tool",
    "none",
    "null",
    "example_tool",
    "dummy_tool",
}


def is_valid_tool_name(name: str) -> bool:
    if not name:
        return False
    return name.strip().lower() not in DUMMY_TOOL_NAMES


def safe_parse_tool_arguments(raw_args: str, tool_name: str = "") -> Dict[str, Any]:
    if not raw_args:
        return {}

    cleaned = raw_args.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    try:
        sanitized = re.sub(r'[\r\n]+', '\\n', cleaned)
        return json.loads(sanitized)
    except Exception:
        pass

    extracted: Dict[str, Any] = {}

    file_path_match = re.search(r'"file_path"\s*:\s*"([^"]+)"', cleaned)
    if file_path_match:
        extracted["file_path"] = file_path_match.group(1)

    content_match = re.search(r'"content"\s*:\s*"(.*)"\s*\}?$', cleaned, re.DOTALL)
    if content_match:
        extracted["content"] = content_match.group(1)

    command_match = re.search(r'"command"\s*:\s*"([^"]+)"', cleaned)
    if command_match:
        extracted["command"] = command_match.group(1)

    desc_match = re.search(r'"description"\s*:\s*"([^"]+)"', cleaned)
    if desc_match:
        extracted["description"] = desc_match.group(1)

    if extracted:
        logger.info("Heuristically recovered JSON arguments for tool '%s'", tool_name)
        return extracted

    logger.warning("Falling back to _raw for tool '%s': %s", tool_name, raw_args[:200])
    return {"_raw": raw_args}


def extract_all_local_tool_invocations(answer: str) -> List[dict]:
    matches = re.finditer(
        r"<local_tool>\s*<name>\s*([^<]+?)\s*</name>\s*"
        r"<arguments>\s*(.*?)\s*</arguments>\s*</local_tool>",
        answer,
        flags=re.IGNORECASE | re.DOTALL,
    )
    invocations = []
    for match in matches:
        tool_name = match.group(1).strip()
        if not is_valid_tool_name(tool_name):
            logger.info("Ignoring dummy/placeholder tool invocation: '%s'", tool_name)
            continue

        raw_args = match.group(2).strip()
        args = safe_parse_tool_arguments(raw_args, tool_name=tool_name)
        invocations.append({
            "name": tool_name,
            "arguments": args,
            "raw": match.group(0),
        })
    return invocations


def extract_local_tool_invocation(answer: str) -> Optional[dict]:
    invocations = extract_all_local_tool_invocations(answer)
    return invocations[0] if invocations else None


class StreamingXmlToolParser:
    def __init__(self):
        self.buffer = ""
        self.in_tool_tag = False

    def feed(self, chunk: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        self.buffer += chunk
        text_chunks: List[str] = []
        tool_calls: List[Dict[str, Any]] = []

        while self.buffer:
            if not self.in_tool_tag:
                start_idx = self.buffer.find("<local_tool>")
                if start_idx == -1:
                    partial_match = False
                    for i in range(len("<local_tool>") - 1, 0, -1):
                        if "<local_tool>"[:i] == self.buffer[-i:]:
                            cutoff = len(self.buffer) - i
                            if cutoff > 0:
                                text_chunks.append(self.buffer[:cutoff])
                                self.buffer = self.buffer[cutoff:]
                            partial_match = True
                            break

                    if not partial_match:
                        text_chunks.append(self.buffer)
                        self.buffer = ""
                    break
                else:
                    if start_idx > 0:
                        text_chunks.append(self.buffer[:start_idx])
                    self.buffer = self.buffer[start_idx:]
                    self.in_tool_tag = True

            if self.in_tool_tag:
                end_idx = self.buffer.find("</local_tool>")
                if end_idx == -1:
                    break

                full_xml = self.buffer[: end_idx + len("</local_tool>")]
                self.buffer = self.buffer[end_idx + len("</local_tool>"):]
                self.in_tool_tag = False

                tool_inv = extract_local_tool_invocation(full_xml)
                if tool_inv:
                    tool_calls.append({
                        "index": 0,
                        "id": f"call_{uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": tool_inv["name"],
                            "arguments": json.dumps(tool_inv["arguments"], ensure_ascii=False),
                        },
                    })

        return text_chunks, tool_calls

    def flush(self) -> List[str]:
        remaining = self.buffer
        self.buffer = ""
        return [remaining] if remaining else []


def clean_user_message(content: Any) -> str:
    if isinstance(content, list):
        text = "\n".join([x.get("text", "") for x in content if isinstance(x, dict)])
    else:
        text = str(content or "")

    tags_to_strip = [
        "available-deferred-tools",
        "available-mcp-tools",
        "workspace-files",
        "environment-details",
        "system-reminder",
        "file-contents",
        "directory-contents",
        "subprocess-output",
        "shell-info",
        "task-description",
    ]
    for tag in tags_to_strip:
        text = re.sub(rf"<{tag}\b.*?>.*?(?:</{tag}>|$)", "", text, flags=re.DOTALL | re.IGNORECASE)

    text = re.sub(r"\[Request interrupted by user\]", "", text)
    return text.strip()


def extract_last_tool_execution_context(
    messages: List[Dict[str, Any]],
    workspace_sync: Optional[Any] = None,
) -> str:
    if not messages:
        return ""

    tool_blocks: List[str] = []
    assistant_tool_call_block: Optional[str] = None

    idx = len(messages) - 1

    while idx >= 0:
        msg = messages[idx]
        if not isinstance(msg, dict):
            idx -= 1
            continue
        role = (msg.get("role") or "").lower()
        content = msg.get("content") or ""

        if role == "user" and not clean_user_message(content):
            idx -= 1
            continue
        if role == "assistant" and (content == "[Tool results received]" or not content):
            idx -= 1
            continue
        break

    assistant_msg_idx = idx
    prev_assistant_calls: Dict[str, dict] = {}
    while assistant_msg_idx >= 0:
        amsg = messages[assistant_msg_idx]
        if isinstance(amsg, dict) and (amsg.get("role") or "").lower() == "assistant":
            for tc in amsg.get("tool_calls") or []:
                if isinstance(tc, dict) and tc.get("id"):
                    prev_assistant_calls[tc["id"]] = tc
            break
        elif isinstance(amsg, dict) and (amsg.get("role") or "").lower() in {"tool", "function"}:
            assistant_msg_idx -= 1
        else:
            break

    while idx >= 0:
        msg = messages[idx]
        if not isinstance(msg, dict):
            idx -= 1
            continue

        role = (msg.get("role") or "").lower()
        if role in {"tool", "function"}:
            tool_id = msg.get("tool_call_id") or msg.get("name") or "unknown"
            content = msg.get("content") or ""
            if isinstance(content, list):
                content = "\n".join([x.get("text", "") for x in content if isinstance(x, dict)])

            matched_tc = prev_assistant_calls.get(tool_id, {})
            fn_info = matched_tc.get("function", {}) if isinstance(matched_tc, dict) else {}
            fn_name = (fn_info.get("name") or "").lower()
            fn_args_str = fn_info.get("arguments") or ""

            from orchestrator.config import get_run_logger

            file_path = None
            parsed_args = {}
            if isinstance(fn_args_str, str) and fn_args_str:
                try:
                    parsed_args = json.loads(fn_args_str)
                    if isinstance(parsed_args, dict):
                        file_path = parsed_args.get("file_path") or parsed_args.get("path")
                except Exception:
                    fp_match = re.search(r'"file_path"\s*:\s*"([^"]+)"', fn_args_str)
                    if fp_match:
                        file_path = fp_match.group(1)
                    parsed_args = {"_raw": fn_args_str}

            get_run_logger().log_tool_call(
                tool_name=fn_name or tool_id,
                arguments=parsed_args if isinstance(parsed_args, dict) else {"args": parsed_args},
                result_summary=content[:300],
                intercepted=False,
            )

            if workspace_sync and (fn_name in {"read", "view", "read_file"} or file_path):
                if not file_path:
                    fp_match = re.search(r'File:\s*([^\n]+)', content)
                    file_path = fp_match.group(1).strip() if fp_match else "read_file.txt"

                desc = workspace_sync.on_tool_read(file_path, content)

                tool_blocks.insert(
                    0,
                    f"[TOOL RESULT ({tool_id})]: File '{file_path}' uploaded and staged (Status: {desc.status.value if desc else 'FAILED'}).\nContent output:\n{content}"
                )
            elif workspace_sync and (fn_name in {"bash", "list_dir", "ls", "dir", "run_bash"}):
                folder_target = getattr(workspace_sync, "root", None) or os.getcwd()
                desc = workspace_sync.on_folder_read(folder_target, content)

                tool_blocks.insert(
                    0,
                    f"[TOOL RESULT ({tool_id})]: Directory listing uploaded and staged (Status: {desc.status.value if desc else 'FAILED'}).\nListing output:\n{content}"
                )
            else:
                tool_blocks.insert(
                    0,
                    f"[TOOL RESULT ({tool_id})]:\n{content}"
                )
            idx -= 1
        else:
            break

    if idx >= 0:
        prev_msg = messages[idx]
        if isinstance(prev_msg, dict) and (prev_msg.get("role") or "").lower() == "assistant":
            if prev_msg.get("tool_calls"):
                assistant_tool_call_block = (
                    f"[ASSISTANT TOOL INVOCATION]:\n"
                    f"{json.dumps(prev_msg.get('tool_calls'), indent=2)}"
                )

    if not tool_blocks:
        return ""

    context_parts = []
    if assistant_tool_call_block:
        context_parts.append(assistant_tool_call_block)
    context_parts.extend(tool_blocks)

    return (
        "=== MOST RECENT TOOL EXECUTION RESULTS ===\n"
        "NOTE: The local client executed the requested tool and returned the following real output.\n"
        "Use this output to answer the user request directly:\n\n"
        + "\n\n".join(context_parts)
        + "\n===========================================\n\n"
    )
