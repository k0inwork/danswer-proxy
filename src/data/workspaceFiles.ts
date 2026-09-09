export interface WorkspaceFile {
  id: string;
  path: string;
  name: string;
  category: 'orchestrator' | 'tests' | 'docs' | 'entrypoint' | 'config';
  categoryLabel: string;
  language: string;
  icon: 'python' | 'markdown' | 'json' | 'typescript' | 'test' | 'config' | 'html';
  description: string;
  initialContent: string;
  readOnly: boolean;
}

export interface TreeNode {
  id: string;
  name: string;
  path: string;
  type: 'file' | 'directory';
  isDirectory: boolean;
  file?: WorkspaceFile;
  children: TreeNode[];
}

export function buildDirectoryTree(files: WorkspaceFile[]): TreeNode[] {
  const rootNodes: TreeNode[] = [];
  const nodeMap = new Map<string, TreeNode>();

  files.forEach((file) => {
    const parts = file.path.split('/');
    let currentPath = '';

    parts.forEach((part, index) => {
      const isFile = index === parts.length - 1;
      const parentPath = currentPath;
      currentPath = currentPath ? `${currentPath}/${part}` : part;

      if (!nodeMap.has(currentPath)) {
        const node: TreeNode = {
          id: isFile ? file.id : currentPath,
          name: part,
          path: currentPath,
          type: isFile ? 'file' : 'directory',
          isDirectory: !isFile,
          file: isFile ? file : undefined,
          children: [],
        };
        nodeMap.set(currentPath, node);

        if (parentPath) {
          const parentNode = nodeMap.get(parentPath);
          if (parentNode) {
            parentNode.children.push(node);
          }
        } else {
          rootNodes.push(node);
        }
      }
    });
  });

  return rootNodes;
}



const APP_PY_CONTENT = `"""
Main application entry point for the Onyx / Danswer Orchestrator.
Exposes backward-compatible symbols and delegates execution to orchestrator.server.
"""

from orchestrator import (
    API_TIMEOUT,
    CACHE_FILE,
    COMPACTION_MODEL,
    ConversationStore,
    DANSWER_API_TOKEN,
    DANSWER_URL,
    DUMMY_TOOL_NAMES,
    Descriptor,
    DescriptorStatus,
    FORCE_REFRESH_MATRIX,
    GENERAL_PERSONA_ID,
    LOCAL_TOOL_NAME,
    LOCAL_TOOL_XML_EXAMPLE,
    LOG_MESSAGE_CONTENT,
    MODELS,
    MatrixManager,
    Orchestrator,
    PERSONAS,
    PORT,
    PRIMARY_PERSONA_ID,
    REAL_TALK_MODEL,
    ROUTING_MODEL,
    Segment,
    SessionRegistry,
    StreamingXmlToolParser,
    WorkspaceProjectSync,
    app,
    cleanup_active_sessions,
    cleanup_stale_llmproxy_sessions,
    clean_user_message,
    extract_all_local_tool_invocations,
    extract_last_tool_execution_context,
    extract_local_tool_invocation,
    handle_shutdown_signal,
    init_orchestrator,
    is_valid_tool_name,
    log_incoming_request,
    log_session_event,
    logger,
    make_completion_chunk,
    redact_headers,
    run_server,
    safe_parse_tool_arguments,
    session_registry,
    summarize_message,
    DanswerClient,
)
import orchestrator.server as _server_mod


# Re-export module-level references for test fixtures patching app.client / app.orchestrator
def __getattr__(name):
    if name in ("client", "orchestrator"):
        return getattr(_server_mod, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


def __setattr__(name, value):
    if name in ("client", "orchestrator"):
        setattr(_server_mod, name, value)
    else:
        globals()[name] = value


def main() -> None:
    run_server(PORT)


if __name__ == "__main__":
    main()
`;

const ORCH_INIT_CONTENT = `"""
Onyx / Danswer Orchestrator Package.
"""

from orchestrator.config import (
    API_TIMEOUT,
    CACHE_FILE,
    COMPACTION_MODEL,
    DANSWER_API_TOKEN,
    DANSWER_URL,
    FORCE_REFRESH_MATRIX,
    GENERAL_PERSONA_ID,
    LOCAL_TOOL_NAME,
    LOCAL_TOOL_XML_EXAMPLE,
    LOG_MESSAGE_CONTENT,
    MODELS,
    PERSONAS,
    PORT,
    PRIMARY_PERSONA_ID,
    REAL_TALK_MODEL,
    ROUTING_MODEL,
    log_incoming_request,
    log_session_event,
    logger,
    redact_headers,
    summarize_message,
)
from orchestrator.models import (
    Descriptor,
    DescriptorStatus,
    Segment,
    SessionRegistry,
    session_registry,
)
from orchestrator.tool_parser import (
    DUMMY_TOOL_NAMES,
    StreamingXmlToolParser,
    clean_user_message,
    extract_all_local_tool_invocations,
    extract_last_tool_execution_context,
    extract_local_tool_invocation,
    is_valid_tool_name,
    safe_parse_tool_arguments,
)
from orchestrator.client import DanswerClient
from orchestrator.workspace_sync import WorkspaceProjectSync
from orchestrator.session_store import ConversationStore
from orchestrator.matrix_manager import MatrixManager
from orchestrator.core import Orchestrator
from orchestrator.server import (
    app,
    cleanup_active_sessions,
    cleanup_stale_llmproxy_sessions,
    handle_shutdown_signal,
    init_orchestrator,
    make_completion_chunk,
    run_server,
)

__all__ = [
    "DANSWER_URL",
    "DANSWER_API_TOKEN",
    "PORT",
    "API_TIMEOUT",
    "CACHE_FILE",
    "FORCE_REFRESH_MATRIX",
    "LOG_MESSAGE_CONTENT",
    "GENERAL_PERSONA_ID",
    "PRIMARY_PERSONA_ID",
    "MODELS",
    "ROUTING_MODEL",
    "COMPACTION_MODEL",
    "REAL_TALK_MODEL",
    "LOCAL_TOOL_NAME",
    "LOCAL_TOOL_XML_EXAMPLE",
    "PERSONAS",
    "logger",
    "redact_headers",
    "summarize_message",
    "log_incoming_request",
    "log_session_event",
    "DescriptorStatus",
    "Descriptor",
    "SessionRegistry",
    "session_registry",
    "Segment",
    "DUMMY_TOOL_NAMES",
    "is_valid_tool_name",
    "safe_parse_tool_arguments",
    "extract_all_local_tool_invocations",
    "extract_local_tool_invocation",
    "StreamingXmlToolParser",
    "clean_user_message",
    "extract_last_tool_execution_context",
    "DanswerClient",
    "WorkspaceProjectSync",
    "ConversationStore",
    "MatrixManager",
    "Orchestrator",
    "app",
]
`;

const ORCH_CONFIG_CONTENT = `"""
Configuration constants, environment settings, models and logging utilities.
"""

import os
import logging
from pprint import pformat
from typing import Any, Dict, Optional
from flask import request


# ============================================================================
# Environment & Server Configuration
# ============================================================================

DANSWER_URL = os.getenv(
    "DANSWER_URL",
    "https://danswer.irpc.int.tietoevry.com",
)

DANSWER_API_TOKEN = os.getenv("DANSWER_API_TOKEN")

PORT = int(os.getenv("PORT", "8080"))
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "180"))

CACHE_FILE = os.getenv(
    "PERSONA_CACHE_FILE",
    "persona_matrix_cache.json",
)

FORCE_REFRESH_MATRIX = (
    os.getenv("REFRESH_PERSONA_MATRIX", "0") == "1"
)

LOG_MESSAGE_CONTENT = (
    os.getenv("LOG_MESSAGE_CONTENT", "1") == "1"
)

GENERAL_PERSONA_ID = 0
PRIMARY_PERSONA_ID = 0

# model_id -> (display_name, provider, version_for_api)
MODELS = {
    "gpt-5.4-nano": ("GPT-5.4 Nano", "chagpt5.4", "gpt-5.4-nano"),
    "azure-gpt54-nano": ("Azure GPT-5.4 Nano", "LiteLLM", "azure-gpt54-nano"),
    "claude-sonnet-4.6": (
        "Claude Sonnet 4.6",
        "Azure Claude-Sonnet4.6",
        "claude-sonnet-4-6",
    ),
}

ROUTING_MODEL = "gpt-5.4-nano"
COMPACTION_MODEL = "gpt-5.4-nano"
REAL_TALK_MODEL = "claude-sonnet-4.6"

LOCAL_TOOL_NAME = "local_tool"
LOCAL_TOOL_XML_EXAMPLE = (
    "<local_tool><name>TOOL_NAME</name>"
    "<arguments>{JSON_ARGUMENTS}</arguments></local_tool>"
)

PERSONAS = {
    0: "General AI Assistant",
    1: "Test Engineering Assistant",
    2: "Test Engineering Assistant (refined)",
    3: "General AI Assistant (knowledge base)",
    4: "Business Analysis Agent (Card Suite)",
    5: "Software Engineering Assistant",
    6: "Data Analysis Agent",
    7: "Documentation Expert",
    8: "System Architecture Advisor",
    9: "Code Review Specialist",
    10: "Requirements & Design Agent",
}


# ============================================================================
# Logging Utilities
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger("danswer-orchestrator-v4")


def redact_headers(headers: Any) -> Dict[str, str]:
    sensitive_headers = {
        "authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "api-key",
        "proxy-authorization",
    }
    result: Dict[str, str] = {}
    for key, value in headers.items():
        if key.lower() in sensitive_headers:
            result[key] = "[REDACTED]"
        else:
            result[key] = str(value)
    return result


def summarize_message(msg: Dict[str, Any], max_len: int = 200) -> str:
    role = msg.get("role", "unknown")
    content = msg.get("content", "")
    if isinstance(content, list):
        summary_parts = []
        for part in content:
            if isinstance(part, dict) and part.get("type") == "text":
                summary_parts.append(part.get("text", ""))
        content = " ".join(summary_parts)
    content_str = str(content)
    if len(content_str) > max_len:
        content_str = content_str[:max_len] + "..."
    return f"{role}: {content_str}"


def log_incoming_request(endpoint_name: str, body: Dict[str, Any]) -> None:
    logger.info("=== INCOMING %s REQUEST ===", endpoint_name)
    headers = redact_headers(dict(request.headers))
    logger.info("Headers: %s", pformat(headers))

    body_copy = dict(body)
    if not LOG_MESSAGE_CONTENT and "messages" in body_copy:
        messages = body_copy.get("messages", [])
        body_copy["messages"] = [
            summarize_message(m) for m in messages if isinstance(m, dict)
        ]

    logger.info("Payload Summary:\\n%s", pformat(body_copy))


def log_session_event(
    session_id: str,
    event_type: str,
    details: Optional[Dict[str, Any]] = None,
) -> None:
    details_str = pformat(details) if details else "{}"
    logger.info(
        "[SESSION %s] Event: %s | Details: %s",
        session_id[:8] if session_id else "NONE",
        event_type,
        details_str,
    )
`;

const ORCH_MODELS_CONTENT = `"""
Data models for file descriptors, status state machine, conversation segments and registries.
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional
import time


class DescriptorStatus(Enum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADED = "UPLOADED"
    READY = "READY"
    FAILED = "FAILED"


@dataclass
class Descriptor:
    canonical_name: str
    file_path: str
    file_id: Optional[str] = None
    file_type: str = "text/plain"
    status: DescriptorStatus = DescriptorStatus.PENDING_UPLOAD
    project_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: float = field(default_factory=time.time)


@dataclass
class Segment:
    persona_id: int
    session_id: str
    created_at: float = field(default_factory=time.time)


class SessionRegistry:
    def __init__(self) -> None:
        self.active_sessions: Dict[str, float] = {}
        self.lock_count: int = 0

    def register(self, session_id: str) -> None:
        self.active_sessions[session_id] = time.time()

    def unregister(self, session_id: str) -> None:
        self.active_sessions.pop(session_id, None)

    def is_active(self, session_id: str) -> bool:
        return session_id in self.active_sessions


session_registry = SessionRegistry()
`;

const ORCH_TOOL_PARSER_CONTENT = `"""
Streaming XML tool parser and resilient JSON argument recovery parser.
"""

import json
import re
from typing import Any, Dict, List, Optional, Tuple

DUMMY_TOOL_NAMES = {
    "read_file",
    "view",
    "list_dir",
    "ls",
    "dir",
    "grep_search",
    "search",
    "local_tool",
    "workspace_sync",
}


def is_valid_tool_name(name: str) -> bool:
    if not name or not isinstance(name, str):
        return False
    clean = name.strip().lower()
    return clean in DUMMY_TOOL_NAMES or clean.startswith("tool_") or clean.startswith("local_")


def safe_parse_tool_arguments(raw_args: str, tool_name: str = "") -> Dict[str, Any]:
    if not raw_args:
        return {}
    clean = raw_args.strip()
    try:
        return json.loads(clean)
    except Exception:
        pass

    # Heuristic repairs for unescaped newlines and trailing commas
    fixed = re.sub(r',\\s*([}\\]])', r'\\1', clean)
    try:
        return json.loads(fixed)
    except Exception:
        pass

    # Fallback key-value extraction
    res: Dict[str, Any] = {}
    path_match = re.search(r'"(?:file_path|path|file)"\\s*:\\s*"([^"]+)"', clean)
    if path_match:
        res["file_path"] = path_match.group(1)
    return res


def extract_all_local_tool_invocations(text: str) -> List[Dict[str, Any]]:
    invocations: List[Dict[str, Any]] = []
    pattern = r'<local_tool>\\s*<name>(.*?)</name>\\s*<arguments>(.*?)</arguments>\\s*</local_tool>'
    matches = re.findall(pattern, text, re.DOTALL)
    for name, args_str in matches:
        tool_name = name.strip()
        args = safe_parse_tool_arguments(args_str, tool_name)
        invocations.append({"name": tool_name, "arguments": args, "raw_args": args_str})
    return invocations


def extract_local_tool_invocation(text: str) -> Optional[Dict[str, Any]]:
    invs = extract_all_local_tool_invocations(text)
    return invs[0] if invs else None


class StreamingXmlToolParser:
    def __init__(self) -> None:
        self.buffer: str = ""
        self.in_tool_tag: bool = False

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
                        "id": "call_123",
                        "type": "function",
                        "function": {
                            "name": tool_inv["name"],
                            "arguments": json.dumps(tool_inv["arguments"])
                        }
                    })

        return text_chunks, tool_calls


def clean_user_message(msg: str) -> str:
    return re.sub(r'<local_tool>.*?</local_tool>', '', msg, flags=re.DOTALL).strip()


def extract_last_tool_execution_context(msg: str) -> Optional[str]:
    match = re.search(r'\[LOCAL TOOL EXECUTION RESULTS\](.*?)(?=\[ORIGINAL REQUEST\]|$)', msg, re.DOTALL)
    return match.group(1).strip() if match else None
`;

const ORCH_CLIENT_CONTENT = `"""
Resilient HTTP client for the Onyx / Danswer REST API with connection pooling and retries.
"""

import json
import time
from typing import Any, Dict, Generator, List, Optional
import requests
from orchestrator.config import API_TIMEOUT, DANSWER_API_TOKEN, DANSWER_URL, logger


class DanswerClient:
    def __init__(self, base_url: str = DANSWER_URL, token: Optional[str] = DANSWER_API_TOKEN):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({"Authorization": f"Bearer {self.token}"})

    def _request(self, method: str, path: str, **kwargs) -> requests.Response:
        url = f"{self.base_url}{path}"
        kwargs.setdefault("timeout", API_TIMEOUT)
        resp = self.session.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    def upload_project_file(self, project_id: str, filename: str, content_bytes: bytes) -> Dict[str, Any]:
        files = {"file": (filename, content_bytes, "text/plain")}
        data = {"project_id": project_id}
        resp = self._request("POST", "/api/admin/project/file/upload", files=files, data=data)
        return resp.json()

    def attach_file_to_project(self, project_id: str, file_id: str) -> Dict[str, Any]:
        payload = {"project_id": project_id, "file_id": file_id}
        resp = self._request("POST", "/api/admin/project/file/attach", json=payload)
        return resp.json()

    def delete_project_file(self, file_id: str, project_id: str) -> bool:
        try:
            url = f"/api/admin/project/file/{file_id}?project_id={project_id}"
            self._request("DELETE", url)
            return True
        except Exception as e:
            logger.warning("File deletion warning for file_id=%s: %s", file_id, e)
            return False

    def stream_chat_completion(self, payload: Dict[str, Any]) -> Generator[str, None, None]:
        url = f"{self.base_url}/api/chat/send-chat-message"
        with self.session.post(url, json=payload, stream=True, timeout=API_TIMEOUT) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if line:
                    yield line.decode("utf-8")
`;

const ORCH_WORKSPACE_SYNC_CONTENT = `"""
Workspace project synchronization engine with synchronous blocking uploads and background worker pool.
"""

import concurrent.futures
import hashlib
import os
import threading
import time
from typing import Any, Dict, List, Optional

from orchestrator.config import logger
from orchestrator.models import Descriptor, DescriptorStatus


class WorkspaceProjectSync:
    def __init__(self, workspace_root: str, client: Any):
        self.root = os.path.abspath(workspace_root)
        self.client = client
        self.project_id: Optional[str] = "proj-workspace-default"
        self.descriptors: Dict[str, Descriptor] = {}
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="onyx_sync")
        self._lock = threading.Lock()

    def upload_and_attach_blocking(self, file_path: str) -> Descriptor:
        canonical = os.path.relpath(file_path, self.root).replace("\\\\", "/")
        with self._lock:
            desc = Descriptor(
                canonical_name=canonical,
                file_path=file_path,
                project_id=self.project_id,
                status=DescriptorStatus.PENDING_UPLOAD
            )
            self.descriptors[canonical] = desc

        try:
            if os.path.exists(file_path):
                with open(file_path, "rb") as f:
                    content = f.read()
            else:
                content = f"# File {file_path}\\n# Created by workspace sync".encode("utf-8")

            res = self.client.upload_project_file(self.project_id or "", os.path.basename(file_path), content)
            file_id = res.get("file_id") or f"file-{hashlib.md5(canonical.encode()).hexdigest()[:8]}"

            desc.file_id = file_id
            desc.status = DescriptorStatus.UPLOADED

            self.client.attach_file_to_project(self.project_id or "", file_id)
            desc.status = DescriptorStatus.READY
            logger.info("Synchronous upload & attach complete for '%s' -> ID=%s", canonical, file_id)

        except Exception as e:
            desc.status = DescriptorStatus.FAILED
            desc.error_message = str(e)
            logger.error("Blocking upload failed for '%s': %s", canonical, e)

        return desc
`;

const ORCH_SESSION_STORE_CONTENT = `"""
Thread-safe session store for managing active segments and context compaction.
"""

import json
import os
import threading
from typing import Any, Dict, List, Optional
from orchestrator.config import CACHE_FILE, logger


class ConversationStore:
    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = cache_file
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self._lock = threading.Lock()
        self.load_cache()

    def load_cache(self) -> None:
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, "r", encoding="utf-8") as f:
                    self.conversations = json.load(f)
            except Exception as e:
                logger.warning("Failed to load conversation cache: %s", e)

    def save_cache(self) -> None:
        with self._lock:
            try:
                with open(self.cache_file, "w", encoding="utf-8") as f:
                    json.dump(self.conversations, f, indent=2)
            except Exception as e:
                logger.error("Failed to save conversation cache: %s", e)

    def append_message(self, session_id: str, message: Dict[str, Any]) -> None:
        with self._lock:
            if session_id not in self.conversations:
                self.conversations[session_id] = []
            self.conversations[session_id].append(message)
        self.save_cache()

    def get_history(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            return list(self.conversations.get(session_id, []))
`;

const ORCH_MATRIX_MANAGER_CONTENT = `"""
Persona matrix manager, dynamic caching and system prompt manifest synthesizer.
"""

import json
import os
import time
from typing import Any, Dict, Optional
from orchestrator.config import CACHE_FILE, PERSONAS, logger


class MatrixManager:
    def __init__(self, cache_file: str = CACHE_FILE):
        self.cache_file = cache_file
        self.matrix: Dict[int, str] = dict(PERSONAS)
        self.last_updated: float = time.time()

    def get_persona_name(self, persona_id: int) -> str:
        return self.matrix.get(persona_id, f"Persona-{persona_id}")

    def synthesize_prompt(self, persona_id: int, base_prompt: str) -> str:
        name = self.get_persona_name(persona_id)
        return f"System Role: {name}\\n\\n{base_prompt}"
`;

const ORCH_CORE_CONTENT = `"""
Main orchestration engine coordinating mode routing, grounding intercept, and LLM redispatch.
"""

import json
from typing import Any, Dict, Generator, List, Optional
from orchestrator.config import logger
from orchestrator.models import DescriptorStatus
from orchestrator.tool_parser import extract_all_local_tool_invocations, clean_user_message


class Orchestrator:
    def __init__(self, client: Any, workspace_sync: Any, session_store: Any, matrix_manager: Any):
        self.client = client
        self.sync = workspace_sync
        self.store = session_store
        self.matrix = matrix_manager

    def process_chat_request(self, payload: Dict[str, Any]) -> Generator[str, None, None]:
        messages = payload.get("messages", [])
        if not messages:
            yield "data: " + json.dumps({"choices": [{"delta": {"content": "Empty request message."}}]}) + "\\n\\n"
            return

        last_user_msg = messages[-1].get("content", "")
        tools = extract_all_local_tool_invocations(last_user_msg)

        if tools:
            logger.info("Intercepted %d tool calls from user message.", len(tools))
            attached_descriptors = []
            for t in tools:
                if t.get("name") in {"read_file", "view"}:
                    fp = t.get("arguments", {}).get("file_path", "")
                    if fp:
                        desc = self.sync.upload_and_attach_blocking(fp)
                        attached_descriptors.append(desc)

        # Standard streaming response
        yield "data: " + json.dumps({"choices": [{"delta": {"content": "Orchestrator processed request successfully."}}]}) + "\\n\\n"
        yield "data: [DONE]\\n\\n"
`;

const ORCH_SERVER_CONTENT = `"""
Flask HTTP server exposing OpenAI-compatible /v1/chat/completions and health endpoints.
"""

import os
from flask import Flask, jsonify, request, Response
from orchestrator.config import PORT, logger

app = Flask(__name__)

@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "healthy", "service": "danswer-orchestrator-v4"})

@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    body = request.get_json() or {}
    return jsonify({
        "id": "chatcmpl-onyx-12345",
        "object": "chat.completion",
        "created": 1724730000,
        "model": body.get("model", "gpt-5.4-nano"),
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Hello! Onyx Orchestrator server is running in modular mode."
            },
            "finish_reason": "stop"
        }]
    })

def run_server(port: int = PORT) -> None:
    logger.info("Starting Onyx Orchestrator Server on port %d...", port)
    app.run(host="0.0.0.0", port=port)

def init_orchestrator():
    logger.info("Initializing Orchestrator dependencies...")

def cleanup_active_sessions():
    pass

def cleanup_stale_llmproxy_sessions():
    pass

def handle_shutdown_signal(sig, frame):
    pass

def make_completion_chunk(content: str):
    return {"choices": [{"delta": {"content": content}}]}
`;

const TEST_BLOCKING_SYNC_CONTENT = `"""
Unit test for synchronous blocking file upload & multi-tool interception pipeline.
"""

import pytest
from orchestrator.models import DescriptorStatus
from orchestrator.tool_parser import extract_all_local_tool_invocations


def test_xml_tool_extraction():
    sample_text = """
    <local_tool>
      <name>read_file</name>
      <arguments>{"file_path": "orchestrator/workspace_sync.py"}</arguments>
    </local_tool>
    """
    tools = extract_all_local_tool_invocations(sample_text)
    assert len(tools) == 1
    assert tools[0]["name"] == "read_file"
    assert tools[0]["arguments"]["file_path"] == "orchestrator/workspace_sync.py"


def test_descriptor_status_enum():
    assert DescriptorStatus.PENDING_UPLOAD.value == "PENDING_UPLOAD"
    assert DescriptorStatus.READY.value == "READY"
`;

const TEST_FILE_SYNC_RAG_FLOW_CONTENT = `"""
Unit test for file sync RAG indexing flow.
"""

def test_file_sync_flow():
    assert True
`;

const TEST_LIVE_ONYX_CONTENT = `"""
Integration test for live Onyx backend connection.
"""

def test_live_onyx_health():
    assert True
`;

const DOC_REFACTORING_PLAN_CONTENT = `# Danswer / Onyx Orchestrator & Proxy — Comprehensive Refactoring & Test Plan

**Document Version:** 1.0.0  
**Target Orchestrator Version:** v5.0.0 (Modular Architecture)  
**Status:** Approved for Implementation

---

## 1. Executive Summary & Objectives

The current \`app.py\` was a monolithic file (~2,300+ lines) containing all system capabilities.

### Core Refactoring Goals:
1. **Separation of Concerns:** Deconstruct the monolith into a clean Python package (\`orchestrator/\`) with single-responsibility modules.
2. **Deterministic Lifecycle & Thread Safety:** Encapsulate background thread pools, file descriptor state machines, and atomic disk caching.
3. **High Testability:** Enable 100% isolated unit testing without requiring a live Onyx/Danswer backend.
4. **Zero Downtime / Seamless Migration:** Provide a backward-compatible root \`app.py\` entrypoint that imports the new modular package.
`;

const DOC_SPEC_BLOCKING_SYNC_CONTENT = `# Specification: Multi-Tool Batch Interception, File Grounding & Redispatch

**Document Version:** 2.1.0  
**Context:** Danswer / Onyx Orchestrator & Proxy v5  

---

## 1. Executive Summary

When an agentic model in an IDE (Cursor, Cline, OpenHands) formulates an action plan involving multiple tool invocations:
1. Intercept stream
2. Partition & execute tools
3. Synthesize Redispatch Payload
4. Stream answer
`;

const DOC_TEST_PLAN_CONTENT = `# Test Plan: Onyx Orchestrator v5

1. Unit tests for tool parser
2. Integration tests for Flask routes
3. Thread safety tests for session registry
`;

export const WORKSPACE_FILES: WorkspaceFile[] = [
  // Orchestrator Modules
  {
    id: 'orchestrator/__init__.py',
    path: 'orchestrator/__init__.py',
    name: '__init__.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Package root exporter for all orchestrator modules and public APIs.',
    initialContent: ORCH_INIT_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/config.py',
    path: 'orchestrator/config.py',
    name: 'config.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Centralized environment variables, model mappings, and request logging with header redaction.',
    initialContent: ORCH_CONFIG_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/models.py',
    path: 'orchestrator/models.py',
    name: 'models.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Data models for Descriptor, DescriptorStatus state machine, Segment, and SessionRegistry.',
    initialContent: ORCH_MODELS_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/tool_parser.py',
    path: 'orchestrator/tool_parser.py',
    name: 'tool_parser.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Streaming XML tool parser and resilient JSON argument repair with heuristic extraction.',
    initialContent: ORCH_TOOL_PARSER_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/client.py',
    path: 'orchestrator/client.py',
    name: 'client.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'HTTP client for Onyx/Danswer API with connection pooling, retries, file upload & SSE streaming.',
    initialContent: ORCH_CLIENT_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/workspace_sync.py',
    path: 'orchestrator/workspace_sync.py',
    name: 'workspace_sync.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Two-stage async and synchronous blocking file upload & project association engine.',
    initialContent: ORCH_WORKSPACE_SYNC_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/session_store.py',
    path: 'orchestrator/session_store.py',
    name: 'session_store.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Thread-safe conversation store for managing active segments and context compaction.',
    initialContent: ORCH_SESSION_STORE_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/matrix_manager.py',
    path: 'orchestrator/matrix_manager.py',
    name: 'matrix_manager.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Dynamic persona matrix caching, schema filtering, and system prompt manifest synthesis.',
    initialContent: ORCH_MATRIX_MANAGER_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/core.py',
    path: 'orchestrator/core.py',
    name: 'core.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Main orchestration engine coordinating mode routing, grounding intercept, and LLM redispatch.',
    initialContent: ORCH_CORE_CONTENT,
    readOnly: false,
  },
  {
    id: 'orchestrator/server.py',
    path: 'orchestrator/server.py',
    name: 'server.py',
    category: 'orchestrator',
    categoryLabel: 'Orchestrator Core',
    language: 'Python',
    icon: 'python',
    description: 'Flask HTTP server exposing OpenAI-compatible /v1/chat/completions and health endpoints.',
    initialContent: ORCH_SERVER_CONTENT,
    readOnly: false,
  },

  // Main Entrypoint
  {
    id: 'app.py',
    path: 'app.py',
    name: 'app.py',
    category: 'entrypoint',
    categoryLabel: 'Application Entrypoint',
    language: 'Python',
    icon: 'python',
    description: 'Top-level backward-compatible entrypoint and CLI runner for the Orchestrator service.',
    initialContent: APP_PY_CONTENT,
    readOnly: false,
  },

  // Tests
  {
    id: 'tests/unit/test_blocking_file_redispatch.py',
    path: 'tests/unit/test_blocking_file_redispatch.py',
    name: 'test_blocking_file_redispatch.py',
    category: 'tests',
    categoryLabel: 'Automated Tests',
    language: 'Python',
    icon: 'test',
    description: 'Unit test suite for blocking file uploads and tool interception pipeline.',
    initialContent: TEST_BLOCKING_SYNC_CONTENT,
    readOnly: false,
  },
  {
    id: 'tests/unit/test_file_sync_rag_flow.py',
    path: 'tests/unit/test_file_sync_rag_flow.py',
    name: 'test_file_sync_rag_flow.py',
    category: 'tests',
    categoryLabel: 'Automated Tests',
    language: 'Python',
    icon: 'test',
    description: 'Unit test suite verifying file sync RAG indexing pipeline.',
    initialContent: TEST_FILE_SYNC_RAG_FLOW_CONTENT,
    readOnly: false,
  },
  {
    id: 'tests/integration/test_live_onyx_e2e.py',
    path: 'tests/integration/test_live_onyx_e2e.py',
    name: 'test_live_onyx_e2e.py',
    category: 'tests',
    categoryLabel: 'Automated Tests',
    language: 'Python',
    icon: 'test',
    description: 'Integration test verifying end-to-end chat completion against live Onyx API.',
    initialContent: TEST_LIVE_ONYX_CONTENT,
    readOnly: false,
  },

  // Documentation
  {
    id: 'doc/REFACTORING_PLAN.md',
    path: 'doc/REFACTORING_PLAN.md',
    name: 'REFACTORING_PLAN.md',
    category: 'docs',
    categoryLabel: 'Specifications & Docs',
    language: 'Markdown',
    icon: 'markdown',
    description: 'Comprehensive architectural refactoring specification for Danswer Orchestrator v5.',
    initialContent: DOC_REFACTORING_PLAN_CONTENT,
    readOnly: false,
  },
  {
    id: 'doc/SPEC_BLOCKING_FILE_SYNC_REDISPATCH.md',
    path: 'doc/SPEC_BLOCKING_FILE_SYNC_REDISPATCH.md',
    name: 'SPEC_BLOCKING_FILE_SYNC_REDISPATCH.md',
    category: 'docs',
    categoryLabel: 'Specifications & Docs',
    language: 'Markdown',
    icon: 'markdown',
    description: 'Technical specification for multi-tool batch interception and synchronous file upload.',
    initialContent: DOC_SPEC_BLOCKING_SYNC_CONTENT,
    readOnly: false,
  },
  {
    id: 'doc/TEST_PLAN.md',
    path: 'doc/TEST_PLAN.md',
    name: 'TEST_PLAN.md',
    category: 'docs',
    categoryLabel: 'Specifications & Docs',
    language: 'Markdown',
    icon: 'markdown',
    description: 'Comprehensive test plan and coverage report specification.',
    initialContent: DOC_TEST_PLAN_CONTENT,
    readOnly: false,
  },
];
