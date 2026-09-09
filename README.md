# Onyx / Danswer Orchestrator & Proxy Workspace

A enterprise-grade AI Orchestrator and OpenAI-compatible SSE proxy server for Onyx (formerly Danswer), paired with an interactive React + TypeScript codebase explorer and workspace file manager.

---

## 📋 Table of Contents

- [Overview](#overview)
- [Key Features](#key-features)
  - [Backend Orchestrator Engine](#backend-orchestrator-engine)
  - [Frontend Workspace Explorer](#frontend-workspace-explorer)
- [Architecture & Package Structure](#architecture--package-structure)
- [Configuration & Environment Variables](#configuration--environment-variables)
- [Quick Start & Setup](#quick-start--setup)
  - [Prerequisites](#prerequisites)
  - [Backend Server Setup](#backend-server-setup)
  - [Frontend Web Client Setup](#frontend-web-client-setup)
- [API Usage Guide & Examples](#api-usage-guide--examples)
  - [Streaming Chat Completions](#streaming-chat-completions)
  - [Non-Streaming Chat Completions](#non-streaming-chat-completions)
  - [Available Models Endpoint](#available-models-endpoint)
  - [Local Tool Execution Interface](#local-tool-execution-interface)
- [Testing & Verification](#testing--verification)
- [License](#license)

---

## 🌟 Overview

The **Onyx / Danswer Orchestrator & Proxy Workspace** acts as an intelligent intermediary proxy between OpenAI API-compatible clients (e.g., custom web UIs, IDE extensions, or agent scripts) and downstream Onyx / Danswer AI backend services.

It enhances standard AI conversation loops with:
1. **Dynamic Persona Matrix Routing**: Automatically detects prompt context and hands off conversations between specialized domain personas (e.g., General Assistant, Software Specialist, Data Analyst, Architecture Advisor).
2. **Context Compaction & Handover Summaries**: Compacts long conversational turns during persona switches to maintain compact context windows while preserving essential facts.
3. **Automated Workspace File Sync**: Monitors local project directories and asynchronously uploads and attaches files to Onyx projects in real time using multi-threaded background pools.
4. **Auto-Grounding Tool Interception**: Intercepts local tool calls (`<local_tool>` tags), streams progress, and automatically performs blocking file syncs for read operations before redispatching queries.
5. **Interactive Developer Workspace UI**: A React 19 + Vite frontend providing tree filtering, code inspection, Markdown rendering, and instant repository ZIP export.

---

## ✨ Key Features

### Backend Orchestrator Engine

- **OpenAI v1 Compatible API**: Exposes `/v1/chat/completions` (supporting both streaming SSE and non-streaming responses) and `/v1/models`.
- **Multi-Persona Context Routing**: Automatically classifies incoming queries against persona manifests using a dedicated classification model (`gpt-5.4-nano`) and transitions context seamlessly.
- **Asynchronous Workspace File Sync Daemon (`WorkspaceProjectSync`)**:
  - Monitors local filesystem changes via timestamp (`mtime`) hashing.
  - Multi-threaded upload and attachment workflow via `ThreadPoolExecutor(max_workers=4)`.
  - File status state machine (`PENDING_UPLOAD` → `UPLOADED` → `READY` / `FAILED`).
  - Polling mechanism (`wait_for_file_processing`) ensuring files finish Onyx vector indexing before attachment.
- **Streaming XML Tool Call Parsing & Argument Repair**:
  - State-machine XML stream parser (`StreamingXmlToolParser`) for extracting `<local_tool>` calls in real time.
  - Multi-stage heuristic JSON repair (`safe_parse_tool_arguments`) handling unescaped quotes, line breaks, and truncated payloads.
- **Resilient Onyx Client (`DanswerClient`)**:
  - Automatic error recovery, request retrying, and header sanitization.
  - Fault-tolerant deletion and project management endpoints with 404 suppression.
- **Atomic Session & Caching Store (`SessionRegistry` & `ConversationStore`)**:
  - Thread-safe session tracking with LRU cache eviction and atomic JSON persistence (`.tmp` + write replace).

### Frontend Workspace Explorer

- **Interactive File Tree Navigation**: Filter by search query or restrict view exclusively to Python modules (`.py`).
- **In-File Search**: Full intra-file search bar (Ctrl+F style) with match counter and previous/next navigation controls.
- **Rich Code & Markdown Viewer**:
  - Full Markdown rendering mode or raw code toggle.
  - Customizable font sizing (zoom in/out) and soft line-wrap toggles.
  - Relative file path and code snippet copy to clipboard.
- **Single File & Full Workspace Export**: Download individual files or archive all workspace files into a ZIP using `JSZip`.

---

## 🏗 Architecture & Package Structure

```
.
├── app.py                          # Main backward-compatible Flask runner
├── orchestrator/                   # Core Python package
│   ├── __init__.py                 # Package exports and version metadata
│   ├── config.py                   # Centralized configuration, personas, models, logging
│   ├── models.py                   # Typed Dataclasses & Enums (Descriptor, Segment, etc.)
│   ├── client.py                   # DanswerClient REST HTTP wrapper with retry policies
│   ├── tool_parser.py              # StreamingXmlToolParser & heuristic JSON repair
│   ├── workspace_sync.py           # WorkspaceProjectSync background daemon & file sync pipeline
│   ├── session_store.py            # SessionRegistry, ConversationStore & JSON persistence
│   ├── matrix_manager.py           # Multi-persona matrix routing logic
│   ├── core.py                     # Main Orchestrator engine (routing, compaction, stream dispatch)
│   └── server.py                   # Flask server exposing OpenAI SSE endpoints
├── src/                            # Frontend React + TypeScript application
│   ├── components/                 # UI Components (PythonFileTree, MarkdownViewer, Modals)
│   ├── data/                       # Workspace file tree definitions & code representations
│   ├── utils/                      # Utilities (zipUtils, diffUtils)
│   ├── App.tsx                     # Main React workspace explorer application
│   ├── index.css                   # Tailwind CSS styling configuration
│   └── main.tsx                    # React app entry point
├── doc/                            # System architecture specs and refactoring plans
│   ├── REFACTORING_PLAN.md         # Architecture specification
│   ├── TEST_PLAN.md                # Automated test specifications
│   └── SPEC_BLOCKING_FILE_SYNC_REDISPATCH.md # Tool intercept specification
├── tests/                          # Test suite
│   ├── unit/                       # Unit tests for parsers, client, stores, sync pipeline
│   ├── integration/                # Integration tests for OpenAI endpoints & Onyx flow
│   └── conftest.py                 # Pytest fixtures and mock Onyx backend server
├── package.json                    # Frontend dependencies and Vite scripts
├── vite.config.ts                  # Vite build and server configuration
└── tsconfig.json                   # TypeScript compiler settings
```

---

## ⚙ Configuration & Environment Variables

Create a `.env` file or export the following environment variables to configure the backend:

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `DANSWER_URL` | `https://danswer.irpc.int.tietoevry.com` | Base URL of the downstream Onyx / Danswer backend. |
| `DANSWER_API_TOKEN` | *(Optional)* | API Bearer token for authenticating against Onyx / Danswer. |
| `PORT` | `8080` | Network port for the Flask Orchestrator server. |
| `API_TIMEOUT` | `180` | Request timeout in seconds for backend HTTP calls. |
| `PERSONA_CACHE_FILE` | `persona_matrix_cache.json` | Path for atomic JSON session & persona persistence. |
| `REFRESH_PERSONA_MATRIX` | `0` | Set to `1` to force refreshing persona matrices on start. |
| `LOG_MESSAGE_CONTENT` | `1` | Set to `1` to print message previews in server logs (`0` to redact). |
| `GEMINI_API_KEY` | *(Optional)* | API Key for Gemini integrations if enabled. |
| `APP_URL` | *(Optional)* | Self-referential URL where the applet is hosted. |

---

## 🚀 Quick Start & Setup

### Prerequisites

- **Python**: 3.10 or higher
- **Node.js / Bun**: Bun 1.0+ or Node.js 18+ (with `npm` / `bun`)

### Backend Server Setup

1. **Install Python dependencies**:
   ```bash
   pip install flask requests pytest
   ```

2. **Run the Flask Orchestrator Server**:
   ```bash
   python3 app.py
   ```
   The server will start listening on `http://0.0.0.0:8080`.

### Frontend Web Client Setup

1. **Install JavaScript dependencies**:
   ```bash
   bun install
   ```
   *(or `npm install`)*

2. **Start the Development Server**:
   ```bash
   bun run dev
   ```
   The Vite preview/dev server will launch locally at `http://localhost:3000`.

3. **Build Frontend for Production**:
   ```bash
   bun run build
   ```

---

## 📋 API Usage Guide & Examples

The Orchestrator exposes standard OpenAI Chat Completions endpoints at `/v1/chat/completions`.

### Streaming Chat Completions

Send a POST request with `"stream": true` to receive a Server-Sent Events (SSE) stream:

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Conversation-ID: session-12345" \
  -d '{
    "model": "gpt-5.4-nano",
    "messages": [
      {"role": "user", "content": "Explain how the workspace file sync daemon operates."}
    ],
    "stream": true
  }'
```

**SSE Output Format**:
```data
data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1710000000,"model":"gpt-5.4-nano","choices":[{"index":0,"delta":{"content":"The workspace file sync daemon monitors..."},"finish_reason":null}]}

data: [DONE]
```

### Non-Streaming Chat Completions

```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Conversation-ID: session-12345" \
  -d '{
    "model": "gpt-5.4-nano",
    "messages": [
      {"role": "user", "content": "List the default personas configured in orchestrator."}
    ],
    "stream": false
  }'
```

### Available Models Endpoint

Query supported models registered in the orchestrator:

```bash
curl http://localhost:8080/v1/models
```

**Response**:
```json
{
  "object": "list",
  "data": [
    {
      "id": "gpt-5.4-nano",
      "object": "model",
      "created": 1710000000,
      "owned_by": "orchestrator"
    },
    {
      "id": "azure-gpt54-nano",
      "object": "model",
      "created": 1710000000,
      "owned_by": "orchestrator"
    },
    {
      "id": "claude-sonnet-4.6",
      "object": "model",
      "created": 1710000000,
      "owned_by": "orchestrator"
    }
  ]
}
```

### Local Tool Execution Interface

When tool manifests are passed in the request payload (`tools: [...]`), the Orchestrator injects local tool formatting instructions into system context.

When the assistant requests local file access or execution, it emits `<local_tool>` tags:

```xml
<local_tool>
  <name>read_file</name>
  <arguments>{"file_path": "orchestrator/workspace_sync.py"}</arguments>
</local_tool>
```

The Orchestrator automatically intercepts this tag, uploads/indexes `orchestrator/workspace_sync.py` to Onyx in a blocking sync step, and transparently redispatches the completion turn with the attached file context!

---

## 🧪 Testing & Verification

### Python Backend Test Suite

The repository includes a full unit and integration test suite using `pytest` and an embedded mock Onyx server:

```bash
python3 -m pytest
```

To run a specific test module:
```bash
python3 -m pytest tests/unit/test_workspace_sync.py
```

### Frontend Type-Checking & Build Verification

Run TypeScript static analysis and Vite production compilation:

```bash
# Type check
bun x tsc --noEmit

# Production build
bun run build
```

---

## 📜 License

This project is released under the MIT License.
