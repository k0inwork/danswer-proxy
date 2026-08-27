# Comprehensive Test Plan & Test Suite Specification

**Document Version:** 1.0.0  
**Target Framework:** `pytest` + `pytest-mock` + `pytest-asyncio`  
**Location:** `/tests/`

---

## 1. Test Architecture & Directory Layout

```
tests/
├── conftest.py                     # Shared fixtures, mock Onyx server, tmp workspace generator
├── unit/
│   ├── test_models.py              # Descriptor and status transitions
│   ├── test_tool_parser.py         # XML stream chunking and JSON heuristic repair
│   ├── test_context_cleaner.py     # XML tag stripping and reverse message inspection
│   ├── test_client.py              # DanswerClient request handling, error wrapping, retries
│   ├── test_workspace_sync.py      # Async callback pipeline, threadpool dispatch, file watching
│   └── test_session_store.py       # Session cache, LRU eviction, atomic file persistence
└── integration/
    ├── test_orchestrator_flow.py   # Full multi-turn persona switching and compaction
    ├── test_openai_api_routes.py   # Flask /v1/chat/completions endpoint (sync & async)
    └── test_sse_streaming.py       # Streaming SSE response validation and tool call emission
```

---

## 2. Mocking Strategy & Shared Fixtures (`conftest.py`)

### 2.1. Mock Onyx Server Fixture
```python
import pytest
import responses

@pytest.fixture
def mock_danswer_api():
    """Intercepts requests to http://localhost:8080 and provides deterministic responses."""
    with responses.RequestsMock(assert_all_requests_are_closed=False) as rsps:
        # Mock /api/persona
        rsps.add(
            responses.GET,
            "http://localhost:8080/api/persona",
            json=[{"id": 0, "name": "General Assistant", "description": "Default"}],
            status=200,
        )
        # Mock /api/user/projects
        rsps.add(
            responses.GET,
            "http://localhost:8080/api/user/projects",
            json=[],
            status=200,
        )
        # Mock /api/user/projects/create
        rsps.add(
            responses.POST,
            "http://localhost:8080/api/user/projects/create",
            json={"id": "mock-proj-123", "name": "Workspace-test-123"},
            status=200,
        )
        # Mock /api/user/projects/file/upload
        rsps.add(
            responses.POST,
            "http://localhost:8080/api/user/projects/file/upload",
            json={"id": "file-uuid-abc-123", "file_type": "plain_text"},
            status=200,
        )
        # Mock /api/user/projects/file/{id} DELETE
        rsps.add(
            responses.DELETE,
            responses.PassthroughResponse if False else None,
            status=204,
        )
        yield rsps
```

### 2.2. Isolated Temporary Workspace Fixture
```python
@pytest.fixture
def temp_workspace(tmp_path):
    """Creates a realistic dummy workspace tree with source files, git dir, and ignored items."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("print('hello world')", encoding="utf-8")
    (src / "utils.py").write_text("def add(a, b): return a + b", encoding="utf-8")
    
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("git config here", encoding="utf-8")
    
    return tmp_path
```

---

## 3. Unit Test Specifications

### 3.1. `test_tool_parser.py`
- **Case 1: Well-Formed XML Tool Calls**:
  - Feed `<local_tool><name>read_file</name><arguments>{"file_path": "foo.py"}</arguments></local_tool>` across arbitrary chunk sizes (1 byte, 5 bytes, whole chunk).
  - Verify complete extraction into `ToolCallInvocation(name='read_file', arguments={'file_path': 'foo.py'})`.
- **Case 2: Fragmented / Stream Splitting Across Tags**:
  - Split `<local_` in chunk 1 and `tool>` in chunk 2. Ensure no tags leak into user text.
- **Case 3: Malformed JSON Repair**:
  - Test unescaped newlines in python code payload within `<arguments>`.
  - Test single quotes vs double quotes.
  - Test trailing unclosed brackets and verify heuristic extraction recovers `file_path` and `content`.

### 3.2. `test_context_cleaner.py`
- **Case 1: System Reminder Stripping**:
  - Ingest messages with `<system-reminder>...</system-reminder>` and ensure it is cleanly stripped.
- **Case 2: Tag Boundary & Parameter Regex**:
  - Ingest `<system-reminder priority="high">some info</system-reminder>`. Ensure parameterized tags are completely removed without leaking into LLM prompt.
- **Case 3: Reverse Message History Scan**:
  - Provide a 30-message history with historical tool results. Ensure `extract_last_tool_execution_context` only extracts the trailing execution round.

### 3.3. `test_workspace_sync.py`
- **Case 1: Tree Map Generation**:
  - Verify `.git`, `__pycache__`, `node_modules`, and binary extensions (`.pyc`, `.zip`, `.png`) are excluded from tree output.
- **Case 2: Async Callback State Progression**:
  - Dispatch a file with `dispatch_file_sync`.
  - Verify status transition: `PENDING_UPLOAD` $\rightarrow$ `UPLOADED` (after mock upload) $\rightarrow$ `READY` (after mock attach).
- **Case 3: Deletion Error Handling**:
  - Mock delete endpoint returning 404. Ensure upload proceeds without raising an exception.
- **Case 4: `get_ready_descriptors()` Filter**:
  - Create 3 descriptors: 1 `READY`, 1 `PENDING_UPLOAD`, 1 `FAILED`.
  - Verify `get_ready_descriptors()` returns only the single `READY` descriptor.

### 3.4. `test_session_store.py`
- **Case 1: Thread-Safe State Mutations**:
  - 10 concurrent threads appending messages to the session registry. Ensure no lost updates or corrupted history.
- **Case 2: Atomic Cache Writes**:
  - Verify cache saving writes to a temporary file before renaming to avoid corruption during interruption.

---

## 4. Integration Test Specifications

### 4.1. `test_openai_api_routes.py`
- **Case 1: Title Generation Fast-Path**:
  - Send POST request to `/v1/chat/completions` with system prompt `"Generate a concise, sentence-case title"`.
  - Verify instantaneous return of synthetic title JSON without making network calls to Onyx.
- **Case 2: Non-Streaming Completion**:
  - Send chat message with `stream: false`.
  - Verify valid OpenAI response structure with choices, message, content, and usage.
- **Case 3: Models Endpoint**:
  - Send GET request to `/v1/models`. Verify all defined model aliases (`gpt-4`, `claude-3-5-sonnet`, `any`) are returned.

### 4.2. `test_sse_streaming.py`
- **Case 1: Streaming Event Stream Protocol Compliance**:
  - Send chat message with `stream: true`.
  - Verify response `Content-Type: text/event-stream`.
  - Verify chunks start with `data: {"id": ...}` and end with `data: [DONE]`.
- **Case 2: In-Stream Tool Call Translation**:
  - Mock LLM streaming raw `<local_tool>` tags.
  - Verify SSE output translates XML chunks into OpenAI `tool_calls` delta objects.

---

## 5. Test Execution Commands & CI Integration

### Running Tests Locally
```bash
# Run all unit tests with verbose output
pytest tests/unit -v

# Run integration tests
pytest tests/integration -v

# Run full test suite with coverage report
pytest --cov=orchestrator --cov-report=term-missing tests/
```

### Coverage Goals
- Core Parsers (`tool_parser.py`, `context_cleaner.py`): **≥ 95% line coverage**
- Workspace Sync & Callbacks (`workspace_sync.py`, `models.py`): **≥ 90% line coverage**
- Server & Routes (`server.py`, `client.py`): **≥ 85% line coverage**
