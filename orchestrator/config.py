"""
Configuration constants, environment settings, models and logging utilities.
"""

import os
import logging
from pprint import pformat
from typing import Any, Dict, Optional
from flask import request

from orchestrator.action_logger import (
    ActionLogger,
    get_run_logger,
    init_run_logger,
)


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

# Eager workspace sync: upload ALL workspace files to the Onyx project at
# startup (and continuously as they appear), instead of only on demand when a
# session actually reads them. Off by default to save uploads; on-demand reads
# still work via the local_tool read interception.
WORKSPACE_EAGER_SYNC = (
    os.getenv("WORKSPACE_EAGER_SYNC", "0") == "1"
)

# Max intercept-and-redispatch tool rounds per client request. Each round the
# model's local_tool calls are executed and the results are sent back to Onyx.
MAX_REDISPATCHES = int(os.getenv("MAX_REDISPATCHES", "6"))

GENERAL_PERSONA_ID = 0
# Onyx precedence rule (upstream resolve_context_user_files): a CUSTOM persona
# injects its own system prompt (e.g. an "analyst" instruction that fights the
# proxy's local_tool protocol) and suppresses Onyx's automatic project-file
# injection. Only the DEFAULT persona (0) inside a project auto-loads all
# project files as chat context. Descriptors explicitly attached by the proxy
# reach the model under any persona, but persona 0 removes the conflicting
# instructions and makes Onyx natively see every synced workspace file.
PRIMARY_PERSONA_ID = 0

# Persona auto-switcher (detect_mode + segment compaction). Disabled by
# default: the routing round-trip adds latency and the switch can drop the
# local-tool instructions. Set PERSONA_SWITCHER=1 to enable.
ENABLE_PERSONA_SWITCHER = os.getenv("PERSONA_SWITCHER", "0") == "1"

# model_id -> (display_name, provider, version_for_api)
MODELS = {
    "claude-sonnet-4.6": (
        "Claude Sonnet 4.6",
        "Azure Claude-Sonnet4.6",
        "claude-sonnet-4-6",
    ),
    "glm-4": ("GLM-4", "LiteLLM", "glm-4"),
    "gpt-5.4-nano": ("GPT-5.4 Nano", "chagpt5.4", "gpt-5.4-nano"),
    "azure-gpt54-nano": ("Azure GPT-5.4 Nano", "LiteLLM", "azure-gpt54-nano"),
}

MODEL_ALIASES = {
    "glm": "glm-4",
    "glm4": "glm-4",
    "glm-4": "glm-4",
    "zhipu": "glm-4",
    "sonnet": "claude-sonnet-4.6",
    "claude": "claude-sonnet-4.6",
    "claude-sonnet": "claude-sonnet-4.6",
    "claude-sonnet-4.6": "claude-sonnet-4.6",
    "sonnet-4.6": "claude-sonnet-4.6",
    "gpt": "gpt-5.4-nano",
    "gpt-5.4": "gpt-5.4-nano",
    "gpt-5.4-nano": "gpt-5.4-nano",
    "gpt54": "gpt-5.4-nano",
    "azure": "azure-gpt54-nano",
    "azure-gpt": "azure-gpt54-nano",
    "azure-gpt54-nano": "azure-gpt54-nano",
}


def resolve_model_key(input_str: str) -> Optional[str]:
    """Resolve user input model string or alias to a valid key in MODELS."""
    if not input_str or not isinstance(input_str, str):
        return None
    cleaned = input_str.strip().lower()

    if cleaned in MODELS:
        return cleaned

    if cleaned in MODEL_ALIASES:
        return MODEL_ALIASES[cleaned]

    model_keys = list(MODELS.keys())
    if cleaned.isdigit():
        idx = int(cleaned) - 1
        if 0 <= idx < len(model_keys):
            return model_keys[idx]

    for key in model_keys:
        if cleaned in key.lower() or key.lower() in cleaned:
            return key

    return None


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
            result[key] = "***REDACTED***"
        else:
            result[key] = value
    return result


def summarize_message(index: int, message: Any) -> Dict[str, Any]:
    if not isinstance(message, dict):
        return {
            "index": index,
            "type": type(message).__name__,
            "value": str(message)[:500],
        }

    content = message.get("content")
    if isinstance(content, str):
        content_info: Dict[str, Any] = {"type": "string", "length": len(content)}
        content_info["preview"] = content[:1000] if LOG_MESSAGE_CONTENT else "***HIDDEN***"
    elif content is None:
        content_info = {"type": "null"}
    elif isinstance(content, list):
        content_info = {"type": "list", "items": len(content)}
    else:
        content_info = {"type": type(content).__name__, "preview": str(content)[:500]}

    result: Dict[str, Any] = {
        "index": index,
        "role": message.get("role"),
        "name": message.get("name"),
        "tool_call_id": message.get("tool_call_id"),
        "keys": list(message.keys()),
        "content": content_info,
    }

    if "tool_calls" in message:
        result["tool_calls"] = message["tool_calls"]
    if "function_call" in message:
        result["function_call"] = message["function_call"]

    return result


def log_incoming_request(data: Dict[str, Any]) -> None:
    messages = data.get("messages") or []
    header_conversation_id = request.headers.get("X-Conversation-ID")
    body_conversation_id = data.get("conversation_id")

    possible_ids = {
        "X-Conversation-ID": header_conversation_id,
        "conversation_id": body_conversation_id,
        "session_id": data.get("session_id"),
        "thread_id": data.get("thread_id"),
        "user": data.get("user"),
    }

    request_info = {
        "method": request.method,
        "path": request.path,
        "remote_addr": request.remote_addr,
        "headers": redact_headers(request.headers),
        "possible_conversation_ids": possible_ids,
        "top_level_keys": list(data.keys()),
        "model": data.get("model"),
        "stream": data.get("stream"),
        "temperature": data.get("temperature"),
        "user": data.get("user"),
        "message_count": len(messages),
        "message_roles": [
            message.get("role") for message in messages if isinstance(message, dict)
        ],
        "messages": [
            summarize_message(index, message)
            for index, message in enumerate(messages)
        ],
    }

    logger.info("INCOMING OPENAI REQUEST\n%s", pformat(request_info, sort_dicts=False))
    get_run_logger().log_action(
        category="API_REQUEST",
        action="INCOMING",
        details={
            "method": request.method,
            "path": request.path,
            "conversation_id": possible_ids.get("conversation_id") or possible_ids.get("X-Conversation-ID"),
            "model": data.get("model"),
            "stream": data.get("stream"),
            "message_count": len(messages),
        },
    )


def log_session_event(
    event: str,
    conversation_id: str,
    session_id: Optional[str] = None,
    persona_id: Optional[int] = None,
) -> None:
    logger.info(
        "SESSION %s conversation_id=%s session_id=%s persona_id=%s",
        event,
        conversation_id,
        session_id,
        persona_id,
    )
    get_run_logger().log_action(
        category="SESSION",
        action=event,
        details={
            "conversation_id": conversation_id,
            "session_id": session_id,
            "persona_id": persona_id,
        },
    )
