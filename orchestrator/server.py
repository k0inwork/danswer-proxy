"""
Flask HTTP Server implementing the OpenAI-compatible completions and models endpoints.
"""

import json
import re
import signal
import sys
from typing import Any, Dict, List, Optional, Tuple
from uuid import uuid4

from flask import Flask, Response, request, stream_with_context

from orchestrator.client import DanswerClient
from orchestrator.config import (
    CACHE_FILE,
    DANSWER_API_TOKEN,
    DANSWER_URL,
    ENABLE_PERSONA_SWITCHER,
    FORCE_REFRESH_MATRIX,
    LOG_MESSAGE_CONTENT,
    MODELS,
    PORT,
    get_run_logger,
    init_run_logger,
    log_incoming_request,
    logger,
    resolve_model_key,
)
from orchestrator.core import Orchestrator
from orchestrator.matrix_manager import MatrixManager
from orchestrator.models import session_registry
from orchestrator.tool_parser import (
    StreamingXmlToolParser,
    clean_user_message,
)
from orchestrator.workspace_sync import WorkspaceProjectSync


app = Flask(__name__)

client: Optional[DanswerClient] = None
orchestrator: Optional[Orchestrator] = None


def make_completion_chunk(
    completion_id: str,
    content: Optional[str] = None,
    role: Optional[str] = None,
    finish_reason: Optional[str] = None,
    tool_calls: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    delta: Dict[str, Any] = {}
    if role is not None:
        delta["role"] = role
    if content is not None:
        delta["content"] = content
    if tool_calls is not None:
        delta["tool_calls"] = tool_calls

    return {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    if orchestrator is None:
        return {"error": "Orchestrator is not initialized"}, 503

    data = request.get_json(silent=True) or {}
    log_incoming_request(data)

    messages = data.get("messages") or []
    external_tools = data.get("tools") or []

    if not messages or not isinstance(messages, list):
        return {"error": "Valid messages list is required"}, 400

    provided_conversation_id = (
        request.headers.get("X-Conversation-ID")
        or data.get("conversation_id")
    )
    if provided_conversation_id:
        conversation_id = provided_conversation_id
    else:
        # Stateless mode: clients that do not manage conversations (they
        # resend full history each request) get a fresh Onyx session per
        # request. This prevents one poisoned/bloated shared Onyx session
        # from leaking stale failures into every later turn.
        conversation_id = f"req-{uuid4().hex[:12]}"

    req_model = data.get("model")
    if req_model and isinstance(req_model, str):
        resolved_req_model = resolve_model_key(req_model)
        if resolved_req_model:
            orchestrator.set_active_model(conversation_id, resolved_req_model)

    stream_requested = data.get("stream", True)
    completion_id = f"chatcmpl-{uuid4().hex}"

    first_system_msg = next((m.get("content", "") for m in messages if isinstance(m, dict) and m.get("role") == "system"), "")
    if isinstance(first_system_msg, str) and "Generate a concise, sentence-case title" in first_system_msg:
        user_snippet = next((m.get("content", "") for m in messages if isinstance(m, dict) and m.get("role") == "user"), "")
        if isinstance(user_snippet, str):
            clean_snippet = clean_user_message(user_snippet).strip().replace("\n", " ")
            clean_snippet = re.sub(r"[^a-zA-Z0-9\s]", "", clean_snippet)[:30].strip()
            title_text = clean_snippet.capitalize() if clean_snippet else "General conversation"
        else:
            title_text = "General conversation"

        title_json = json.dumps({"title": title_text})
        logger.info("Fast-pathing title generation locally: %s", title_json)
        get_run_logger().log_action(
            category="FAST_PATH",
            action="TITLE_GENERATE",
            details={"title": title_text, "conversation_id": conversation_id},
        )

        if not stream_requested:
            return Response(
                json.dumps({
                    "id": completion_id,
                    "object": "chat.completion",
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": title_json},
                        "finish_reason": "stop",
                    }],
                    "conversation_id": conversation_id,
                }, ensure_ascii=False),
                mimetype="application/json",
            )
        else:
            def generate_title_stream():
                chunk_msg = make_completion_chunk(
                    completion_id=completion_id,
                    role="assistant",
                    content=title_json,
                    finish_reason="stop",
                )
                yield f"data: {json.dumps(chunk_msg, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return Response(
                generate_title_stream(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

    # OpenAI-compatible clients in agentic mode (e.g. openclaude) send an
    # automatic "continue the task" nudge after every answer. The proxy never
    # leaves work pending between requests (tool rounds complete inside one
    # request), so these are always spurious: answer locally instead of
    # launching a full Onyx invocation that would go looking for a task.
    last_user_msg = next(
        (m.get("content", "") for m in reversed(messages) if isinstance(m, dict) and m.get("role") == "user"),
        "",
    )
    if isinstance(last_user_msg, str):
        cleaned_last = clean_user_message(last_user_msg).strip().lower()
        is_continuation_nudge = len(cleaned_last) < 300 and (
            "continue with the task" in cleaned_last
            or ("resume" in cleaned_last and "thought" in cleaned_last)
        )
        if is_continuation_nudge:
            noop_text = "Nothing is pending — the previous task completed fully."
            logger.info("Fast-pathing client continuation nudge locally (no Onyx call).")
            get_run_logger().log_action(
                category="FAST_PATH",
                action="CONTINUATION_NUDGE",
                details={"conversation_id": conversation_id},
            )
            if not stream_requested:
                return Response(
                    json.dumps({
                        "id": completion_id,
                        "object": "chat.completion",
                        "choices": [{
                            "index": 0,
                            "message": {"role": "assistant", "content": noop_text},
                            "finish_reason": "stop",
                        }],
                        "conversation_id": conversation_id,
                    }, ensure_ascii=False),
                    mimetype="application/json",
                )

            def generate_noop_stream():
                chunk_msg = make_completion_chunk(
                    completion_id=completion_id,
                    role="assistant",
                    content=noop_text,
                    finish_reason="stop",
                )
                yield f"data: {json.dumps(chunk_msg, ensure_ascii=False)}\n\n"
                yield "data: [DONE]\n\n"

            return Response(
                generate_noop_stream(),
                mimetype="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                },
            )

    if stream_requested is False:
        try:
            full_text = "".join(
                orchestrator.process_query(
                    conversation_id=conversation_id,
                    messages=messages,
                    external_tools=external_tools,
                )
            )
            tool_invocations = DanswerClient.extract_all_local_tool_invocations(full_text)

            if tool_invocations:
                openai_tool_calls = []
                clean_content = full_text
                for idx, inv in enumerate(tool_invocations):
                    get_run_logger().log_tool_call(
                        tool_name=inv["name"],
                        arguments=inv["arguments"],
                        result_summary="Converted XML tool call to OpenAI format",
                        intercepted=False,
                    )
                    openai_tool_calls.append({
                        "index": idx,
                        "id": f"call_{uuid4().hex[:8]}",
                        "type": "function",
                        "function": {
                            "name": inv["name"],
                            "arguments": json.dumps(inv["arguments"], ensure_ascii=False) if isinstance(inv["arguments"], dict) else str(inv["arguments"]),
                        },
                    })
                    raw_tag = inv.get("raw")
                    if raw_tag and raw_tag in clean_content:
                        clean_content = clean_content.replace(raw_tag, "")

                clean_content = clean_content.strip()
                response_body = {
                    "id": completion_id,
                    "object": "chat.completion",
                    "choices": [{
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": clean_content or None,
                            "tool_calls": openai_tool_calls,
                        },
                        "finish_reason": "tool_calls",
                    }],
                    "conversation_id": conversation_id,
                }
            else:
                response_body = {
                    "id": completion_id,
                    "object": "chat.completion",
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": full_text},
                        "finish_reason": "stop",
                    }],
                    "conversation_id": conversation_id,
                }

            return Response(
                json.dumps(response_body, ensure_ascii=False),
                mimetype="application/json",
                headers={"X-Conversation-ID": conversation_id},
            )
        except Exception as exc:
            logger.exception("Non-streaming request failed")
            return {"error": str(exc), "conversation_id": conversation_id}, 500

    def _with_heartbeats(source_gen, interval: float = 10.0):
        """Wrap a text-chunk generator so the SSE stream emits an SSE comment
        keep-alive whenever nothing has been produced for `interval` seconds.
        Keeps clients (e.g. openclaude) from timing out during long Onyx calls
        and blocking workspace syncs. SSE comments are ignored by OpenAI
        clients and never reach the model or the chat content."""
        import queue as _queue
        import threading as _threading

        q: _queue.Queue = _queue.Queue()
        _DONE = object()

        def _pump():
            try:
                for chunk in source_gen:
                    q.put(chunk)
            except Exception as exc:
                q.put(exc)
            finally:
                q.put(_DONE)

        pump_thread = _threading.Thread(target=_pump, daemon=True, name="sse-heartbeat-pump")
        pump_thread.start()

        while True:
            try:
                item = q.get(timeout=interval)
            except _queue.Empty:
                yield ": keep-alive\n\n"
                continue
            if item is _DONE:
                break
            if isinstance(item, Exception):
                raise item
            yield item

    @stream_with_context
    def generate_sse():
        first_chunk = True
        try:
            parser = StreamingXmlToolParser()
            tool_calls_emitted = False

            for chunk in _with_heartbeats(
                orchestrator.process_query(
                    conversation_id=conversation_id,
                    messages=messages,
                    external_tools=external_tools,
                )
            ):
                text_chunks, tool_calls = parser.feed(chunk)

                for text in text_chunks:
                    chunk_msg = make_completion_chunk(
                        completion_id=completion_id,
                        role="assistant" if first_chunk else None,
                        content=text,
                    )
                    first_chunk = False
                    yield f"data: {json.dumps(chunk_msg, ensure_ascii=False)}\n\n"

                for tool_call in tool_calls:
                    tool_calls_emitted = True
                    fn_info = tool_call.get("function", {})
                    fn_name = fn_info.get("name", "")
                    fn_args_str = fn_info.get("arguments", "{}")
                    try:
                        fn_args = json.loads(fn_args_str) if isinstance(fn_args_str, str) else fn_args_str
                    except Exception:
                        fn_args = {"_raw": fn_args_str}

                    get_run_logger().log_tool_call(
                        tool_name=fn_name,
                        arguments=fn_args if isinstance(fn_args, dict) else {"args": fn_args},
                        result_summary="Converted XML tool call to OpenAI format",
                        intercepted=False,
                    )

                    chunk_msg = make_completion_chunk(
                        completion_id=completion_id,
                        role="assistant" if first_chunk else None,
                        tool_calls=[tool_call],
                    )
                    first_chunk = False
                    yield f"data: {json.dumps(chunk_msg, ensure_ascii=False)}\n\n"

            for remaining_text in parser.flush():
                chunk_msg = make_completion_chunk(
                    completion_id=completion_id,
                    role="assistant" if first_chunk else None,
                    content=remaining_text,
                )
                first_chunk = False
                yield f"data: {json.dumps(chunk_msg, ensure_ascii=False)}\n\n"

            finish_reason = "tool_calls" if tool_calls_emitted or parser.in_tool_tag else "stop"
            final_chunk = make_completion_chunk(completion_id=completion_id, finish_reason=finish_reason)
            yield f"data: {json.dumps(final_chunk)}\n\n"
            yield "data: [DONE]\n\n"

        except Exception as exc:
            logger.exception("Streaming request failed directly: %s", exc)
            error_msg = f"\n\n[Danswer / Upstream Exception: {exc}]\n"
            error_chunk = make_completion_chunk(
                completion_id=completion_id,
                role="assistant" if first_chunk else None,
                content=error_msg,
                finish_reason="stop",
            )
            yield f"data: {json.dumps(error_chunk, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"

    return Response(
        generate_sse(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Conversation-ID": conversation_id,
            "Access-Control-Expose-Headers": "X-Conversation-ID",
        },
    )


@app.route("/v1/models", methods=["GET"])
@app.route("/api/models", methods=["GET"])
def list_models():
    model_entries = []

    for model_key in MODELS.keys():
        model_entries.append({
            "id": model_key,
            "object": "model",
            "created": 1700000000,
            "owned_by": "danswer-orchestrator",
            "permission": [],
            "root": model_key,
            "parent": None,
        })

    return Response(
        json.dumps({"object": "list", "data": model_entries}, ensure_ascii=False),
        mimetype="application/json",
    )


@app.route("/api/tags", methods=["GET"])
def ollama_tags():
    models_list = []
    for model_key, model_info in MODELS.items():
        disp_name = model_info[0]
        models_list.append({
            "name": model_key,
            "model": model_key,
            "modified_at": "2026-01-01T00:00:00Z",
            "size": 0,
            "digest": f"sha256:{model_key}",
            "details": {
                "parent_model": "",
                "format": "gguf",
                "family": "danswer",
                "families": ["danswer"],
                "parameter_size": disp_name,
                "quantization_level": "default",
            },
        })

    return Response(
        json.dumps({"models": models_list}, ensure_ascii=False),
        mimetype="application/json",
    )


@app.route("/api/version", methods=["GET"])
def ollama_version():
    return Response(
        json.dumps({"version": "0.3.0"}),
        mimetype="application/json",
    )


@app.route("/health", methods=["GET"])
def health():
    return {
        "status": "ok",
        "version": "4.5.0",
        "danswer_url": DANSWER_URL,
        "orchestrator_initialized": (orchestrator is not None),
        "active_tracked_sessions": session_registry.count(),
    }


def cleanup_active_sessions() -> None:
    if client is None:
        return
    active_ids = session_registry.get_all()
    logger.info("Starting shutdown cleanup for %d active tracked session(s)", len(active_ids))
    for sid in active_ids:
        try:
            client.delete_chat_session(sid, kind="shutdown_cleanup")
        except Exception as e:
            logger.warning("Failed to delete session=%s during shutdown: %s", sid, e)
    logger.info("ONYX SESSION CLEANUP remaining=%d", session_registry.count())


def cleanup_stale_llmproxy_sessions(d_client: DanswerClient) -> None:
    try:
        logger.info("Scanning for old llmproxy sessions to erase...")
        sessions = d_client.fetch_chat_sessions()
        count = 0
        for s in sessions:
            desc = s.get("description") or s.get("chat_session_name") or ""
            if desc.startswith("llmproxy:"):
                sid = s.get("id") or s.get("chat_session_id")
                if sid:
                    try:
                        d_client.delete_chat_session(str(sid), kind="stale_startup_cleanup")
                        count += 1
                        logger.info("Erased stale session id=%s desc=%s", sid, desc)
                    except Exception as e:
                        logger.warning("Failed to erase stale session id=%s: %s", sid, e)
        logger.info("Cleaned up %d stale llmproxy sessions.", count)
    except Exception as exc:
        logger.warning("Could not complete automatic cleanup of llmproxy sessions: %s", exc)


def handle_shutdown_signal(signum, frame):
    logger.info("Received shutdown signal (%s). Performing cleanup...", signum)
    cleanup_active_sessions()
    sys.exit(0)


def init_orchestrator(
    danswer_url: str = DANSWER_URL,
    danswer_token: Optional[str] = DANSWER_API_TOKEN,
    workspace_root: Optional[str] = None,
) -> Tuple[DanswerClient, Orchestrator]:
    global client, orchestrator

    if not danswer_token:
        print("DANSWER_API_TOKEN environment variable is required", file=sys.stderr)
        sys.exit(1)

    import os
    root_path = workspace_root or os.getcwd()
    init_run_logger(workspace_root=root_path)

    logger.info("Connecting to Onyx URL: %s", danswer_url)
    client = DanswerClient(danswer_url=danswer_url, api_token=danswer_token)

    cleanup_stale_llmproxy_sessions(client)

    if ENABLE_PERSONA_SWITCHER:
        matrix_manager = MatrixManager(client=client, cache_file=CACHE_FILE)
        routing_manifest, tool_ids = matrix_manager.get_or_build_matrix(
            force_refresh=FORCE_REFRESH_MATRIX
        )
    else:
        # Persona routing disabled: skip matrix construction entirely.
        routing_manifest, tool_ids = "{}", None

    workspace_sync = WorkspaceProjectSync(workspace_root=root_path, client=client)
    workspace_sync.initialize_project()

    orchestrator = Orchestrator(
        client=client,
        routing_manifest=routing_manifest,
        tool_ids=tool_ids,
        workspace_sync=workspace_sync,
    )

    logger.info(
        "Loaded %s global tool IDs (persona_switcher=%s)",
        len(tool_ids or []),
        "on" if ENABLE_PERSONA_SWITCHER else "off",
    )
    return client, orchestrator


def run_server(port: int = PORT, workspace_root: Optional[str] = None) -> None:
    signal.signal(signal.SIGINT, handle_shutdown_signal)
    signal.signal(signal.SIGTERM, handle_shutdown_signal)

    init_orchestrator(workspace_root=workspace_root)

    logger.info("API endpoint: http://0.0.0.0:%s/v1/chat/completions", port)

    try:
        app.run(host="0.0.0.0", port=port, threaded=True)
    finally:
        cleanup_active_sessions()
