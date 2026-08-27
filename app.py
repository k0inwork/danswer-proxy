"""
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
