# Specification: Multi-Tool Batch Interception, File Grounding & Redispatch

**Document Version:** 2.1.0  
**Context:** Danswer / Onyx Orchestrator & Proxy v5  
**Core Mechanism:** Multi-Tool Partitioning $\rightarrow$ Local Tool Execution $\rightarrow$ Synchronous File Sync $\rightarrow$ Synthesized Prompt Redispatch (Same Persona)

---

## 1. Executive Summary

When an agentic model in an IDE (Cursor, Cline, OpenHands) formulates an action plan involving multiple tool invocations (e.g. reconnaissance + file reading):
1. **The LLM emits a tool batch:** e.g. `<local_tool><name>list_dir</name><arguments>{"path": "auth"}</arguments></local_tool>` followed by `<local_tool><name>read_file</name><arguments>{"file_path": "auth/jwt.py"}</arguments></local_tool>`.
2. **We Intercept the Stream:** The Orchestrator intercepts the batch before emitting partial tool calls to the client.
3. **Partition & Execute Tools:**
   - **Non-Read Tools (`list_dir`, `grep_search`):** Executed locally against the workspace disk to capture real output.
   - **Read Tools (`read_file`, `view`):** Uploaded and attached synchronously to the Onyx project via `WorkspaceProjectSync.upload_and_attach_blocking()`.
4. **Synthesize Redispatch Payload:**
   - Prepend file attachment headers: `FILE <path> was attached as <canonical_tag>`
   - Include real execution outputs under `[LOCAL TOOL EXECUTION RESULTS]`
   - Retain the original query context under `[ORIGINAL REQUEST]`
5. **Redispatch In-Context:** The query is redispatched to Onyx (`/api/chat/send-chat-message`) in the **active persona and session** with `file_descriptors` updated to include all newly attached files.
6. **Streaming Delivery:** The final grounded answer streams seamlessly to the client IDE.

---

## 2. Sequence Diagram

```
[Client / IDE]                     [Orchestrator Proxy]                   [Workspace / Onyx Backend]
      |                                      |                                       |
      | 1. "Audit auth/jwt.py in security"   |                                       |
      |------------------------------------->|                                       |
      |                                      | 2. Initial Turn -> Onyx               |
      |                                      |-------------------------------------->|
      |                                      |<--------------------------------------|
      |                                      | 3. Emits Batch:                       |
      |                                      |    - Call 1: list_dir("security")     |
      |                                      |    - Call 2: read_file("jwt.py")      |
      |                                      |    [INTERCEPT: Pause Client Stream]   |
      |                                      |                                       |
      |                                      | 4. Execute Call 1 locally (disk)      |
      |                                      |    -> "jwt.py, keys.py"               |
      |                                      |                                       |
      |                                      | 5. BLOCKING Upload & Attach Call 2    |
      |                                      |-------------------------------------->| POST /file/upload
      |                                      |<--------------------------------------| Return file_id="file-99"
      |                                      |-------------------------------------->| POST /projects/attach
      |                                      |<--------------------------------------| Status -> READY
      |                                      |                                       |
      |                                      | 6. Synthesize Redispatch Payload:     |
      |                                      |    - FILE jwt.py attached as FILE_... |
      |                                      |    - Tool Results (list_dir & attach) |
      |                                      |    - file_descriptors=[{"id":"f-99"}] |
      |                                      |                                       |
      |                                      | 7. REDISPATCH Query to Onyx:          |
      |                                      |-------------------------------------->| (Onyx RAG Indexes File)
      |                                      |<--------------------------------------| (Grounded answer stream)
      | 8. Streams complete grounded answer  | 8. Forward streamed grounded response |
      |<-------------------------------------|---------------------------------------|
```

---

## 3. Implementation Architecture

### 3.1 Local Tool Execution & Workspace Sync (`app.py`)
```python
def execute_local_non_read_tool(self, tool_name: str, args: Dict[str, Any]) -> str:
    """Executes non-read tools (list_dir, grep_search) against local workspace disk."""
    t_name = (tool_name or "").lower().strip()
    if t_name in {"list_dir", "ls", "dir"}:
        req_path = args.get("path") or "."
        target_dir = os.path.join(self.root, req_path) if not os.path.isabs(req_path) else req_path
        if os.path.exists(target_dir) and os.path.isdir(target_dir):
            entries = sorted(os.listdir(target_dir))
            return f"Directory listing of '{req_path}':\n" + "\n".join(entries[:100])
        return f"Directory not found: '{req_path}'"
    ...
```

### 3.2 Multi-Tool Batch Interception & Synthesized Redispatch (`app.py`)
```python
all_tools = DanswerClient.extract_all_local_tool_invocations(buffered_output)
if all_tools:
    has_read_tool = any(is_read_tool(t) for t in all_tools)
    if has_read_tool:
        attached_headers = []
        tool_result_entries = []

        for t in all_tools:
            if is_read_tool(t):
                desc = self.workspace_sync.upload_and_attach_blocking(t_fp)
                canonical = desc.canonical_name if desc else ...
                attached_headers.append(f"FILE {t_fp} was attached as {canonical}")
                tool_result_entries.append(f"- Tool '{t['name']}' ({t_fp}): Attached and indexed as {canonical}.")
            else:
                res_output = self.workspace_sync.execute_local_non_read_tool(t['name'], t_args)
                tool_result_entries.append(f"- Tool '{t['name']}' output:\n{res_output}")

        current_message_to_send = (
            "\n".join(attached_headers) + "\n\n"
            "[LOCAL TOOL EXECUTION RESULTS]:\n" + "\n\n".join(tool_result_entries) + "\n\n"
            f"[ORIGINAL REQUEST]:\n{message_for_persona}"
        )
        redispatch_count += 1
```

---

## 4. Verification & Testing

### 4.1 Automated Unit Tests
```bash
python3 -m unittest tests/unit/test_blocking_file_redispatch.py
```

### 4.2 End-to-End Suite
```bash
python3 -m unittest tests/unit/test_blocking_file_redispatch.py tests/unit/test_file_sync_rag_flow.py tests/integration/test_live_onyx_e2e.py
```
