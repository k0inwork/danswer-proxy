# Danswer / Onyx Orchestrator & Proxy — Comprehensive Refactoring & Test Plan

**Document Version:** 1.0.0  
**Target Orchestrator Version:** v5.0.0 (Modular Architecture)  
**Status:** Approved for Implementation

---

## 1. Executive Summary & Objectives

The current `app.py` is a monolithic file (~2,300+ lines) containing all system capabilities:
- Low-level HTTP requests and retry logic
- XML stream parsing and JSON argument repair
- Asynchronous workspace file synchronization and daemon polling
- Session management, persona routing, and conversation compaction
- Flask web server with OpenAI-compatible SSE endpoints

### Core Refactoring Goals:
1. **Separation of Concerns:** Deconstruct the monolith into a clean Python package (`orchestrator/`) with single-responsibility modules.
2. **Deterministic Lifecycle & Thread Safety:** Encapsulate background thread pools, file descriptor state machines, and atomic disk caching.
3. **High Testability:** Enable 100% isolated unit testing without requiring a live Onyx/Danswer backend.
4. **Zero Downtime / Seamless Migration:** Provide a backward-compatible root `app.py` entrypoint that imports the new modular package.

---

## 2. Target Package Structure

```
danswer-orchestrator/
├── app.py                          # Backwards-compatible root runner (entry point)
├── doc/
│   ├── REFACTORING_PLAN.md         # This specification document
│   ├── TEST_PLAN.md                # Comprehensive test specifications and fixtures
│   └── SPEC_LAZY_FILE_SYNC.md      # Protocol & descriptor specification
├── orchestrator/                   # Core modular package
│   ├── __init__.py                 # Package exports and version metadata
│   ├── config.py                   # Environment vars, constants, models, personas
│   ├── models.py                   # Dataclasses & Enums (Descriptor, DescriptorStatus, etc.)
│   ├── client.py                   # DanswerClient (HTTP session, retry policies, endpoints)
│   ├── tool_parser.py              # StreamingXmlToolParser & argument recovery parsers
│   ├── context_cleaner.py          # Message sanitization, XML stripping & tool extraction
│   ├── workspace_sync.py           # WorkspaceProjectSync, watcher daemon & async callback pipeline
│   ├── session_store.py            # SessionRegistry, ConversationStore, atomic JSON caching
│   ├── matrix_manager.py           # PersonaMatrixManager & persona route detection
│   ├── core.py                     # Main Orchestrator engine (prompt building, stream dispatch)
│   └── server.py                   # Flask application, SSE streaming routes, /v1 endpoints
└── tests/                          # Automated test suite
    ├── __init__.py
    ├── conftest.py                 # Pytest fixtures, mock Onyx server, tmp workspaces
    ├── unit/
    │   ├── test_models.py
    │   ├── test_tool_parser.py
    │   ├── test_context_cleaner.py
    │   ├── test_client.py
    │   ├── test_workspace_sync.py
    │   └── test_session_store.py
    └── integration/
        ├── test_orchestrator_flow.py
        ├── test_openai_api_routes.py
        └── test_sse_streaming.py
```

---

## 3. Module Responsibilities & Detailed Interface Contracts

### 3.1. `orchestrator/config.py`
- **Scope:** Centralized configuration and environment variable loading.
- **Key Definitions:**
  - `DANSWER_URL`, `REAL_TALK_MODEL`, `API_TIMEOUT`, `DEBUG_PROMPTS`
  - Model routing dictionaries (`MODELS`, `MODELS_DESC`)
  - Default Persona templates and fallback mappings
  - Ignored directories/extensions for workspace scanning

### 3.2. `orchestrator/models.py`
- **Scope:** Immutable data structures and typed representations.
- **Key Components:**
  - `DescriptorStatus` (Enum: `PENDING_UPLOAD`, `UPLOADED`, `READY`, `FAILED`)
  - `Descriptor` (Dataclass: `canonical_name`, `file_path`, `file_id`, `file_type`, `status`, `project_id`, `error_message`)
  - `ToolCallInvocation` (Dataclass: `id`, `name`, `arguments`, `raw_xml`)
  - `ConversationSegment` (Dataclass: `persona_id`, `session_id`, `inherited_context`)

### 3.3. `orchestrator/client.py`
- **Scope:** High-resilience API client for the Onyx/Danswer REST interface.
- **Key Methods:**
  - `_safe_request(method, url, **kwargs)` with status-code handling
  - `get_user_projects()`, `create_project()`, `get_project_files()`
  - `upload_project_file(project_id, filename, content_bytes)`
  - `attach_file_to_project(project_id, file_id)`
  - `delete_project_file(file_id, project_id)` (Fault-tolerant with 404 suppression)
  - `send_message(...)` & `iter_stream_text(...)`

### 3.4. `orchestrator/tool_parser.py`
- **Scope:** Real-time XML streaming parser and JSON argument repair.
- **Key Components:**
  - `StreamingXmlToolParser`: Buffer-based state machine for `<local_tool>` tags.
  - `safe_parse_tool_arguments(raw_args, tool_name)`: Multi-stage heuristic parser repairing unescaped newlines, nested quotes, and trailing parameters.

### 3.5. `orchestrator/context_cleaner.py`
- **Scope:** Inbound message sanitization and context extraction.
- **Key Functions:**
  - `clean_user_message(content)`: Strips `<system-reminder>`, `<available-deferred-tools>`, and CLI metadata.
  - `extract_last_tool_execution_context(messages, workspace_sync)`: Reverse-scans message history to extract only recent tool execution blocks.

### 3.6. `orchestrator/workspace_sync.py`
- **Scope:** Per-directory Onyx project isolation and async file upload/attachment pipeline.
- **Key Features:**
  - Dedicated `ThreadPoolExecutor(max_workers=4, thread_name_prefix="onyx_sync")`
  - Callback workflow: `dispatch_file_sync` $\rightarrow$ `_async_upload_task` $\rightarrow$ `_on_upload_complete` $\rightarrow$ `_async_attach_task` $\rightarrow$ `_on_attach_complete`
  - Timestamp-based (`mtime`) cache invalidation to minimize redundant SHA256 computations
  - Background watcher daemon with graceful `shutdown()` support
  - Atomic JSON cache writes (`.tmp` + atomic rename)

### 3.7. `orchestrator/session_store.py` & `matrix_manager.py`
- **Scope:** Multi-turn session tracking and persona routing.
- **Key Components:**
  - Thread-safe `SessionRegistry` with LRU eviction and memory bounds
  - `MatrixManager` for multi-persona mode detection and segment inheritance

### 3.8. `orchestrator/server.py`
- **Scope:** Flask REST and SSE server.
- **Endpoints:**
  - `POST /v1/chat/completions`: Streaming and non-streaming chat endpoint
  - `GET /v1/models`: OpenAI model registry
  - `GET /health`: Health check and diagnostic metrics

---

## 4. Migration & Implementation Phases

| Phase | Milestone | Deliverables | Verification Criteria |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Module Extraction | `config.py`, `models.py`, `tool_parser.py`, `client.py` | 100% unit test pass rate on parsers & HTTP adapters |
| **Phase 2** | Sync Pipeline Isolation | `workspace_sync.py`, `context_cleaner.py`, `session_store.py` | Thread-safety tests and simulated async upload callbacks pass |
| **Phase 3** | Core & Server Wiring | `core.py`, `server.py`, root `app.py` wrapper | End-to-end SSE streaming tests with mock Onyx server pass |
| **Phase 4** | Performance & Hardening | `mtime` check optimizations, atomic caching, shutdown signals | Benchmarked zero memory leaks and clean background daemon teardown |

---

## 5. Backward Compatibility Guarantee

To ensure existing deployment scripts, Dockerfiles, and developer workflows continue working without modification:
- The root `app.py` will remain as a lightweight runner:
  ```python
  #!/usr/bin/env python3
  from orchestrator.server import app, orchestrator

  if __name__ == "__main__":
      import sys
      from orchestrator.config import SERVER_PORT
      app.run(host="0.0.0.0", port=SERVER_PORT, debug=False, threaded=True)
  ```
- All environment variable names (`DANSWER_URL`, `DANSWER_API_KEY`, etc.) remain 100% identical.
