export interface ChangelogItem {
  id: string;
  category: 'Fix' | 'Performance' | 'Resilience' | 'Sanitization' | 'Concurrency' | 'Tooling & Execution';
  title: string;
  severity: 'Critical' | 'High' | 'Medium';
  symptomInLogs: string;
  rootCause: string;
  solution: string;
  diffHighlight: {
    file: string;
    before: string;
    after: string;
  };
}

export const CHANGELOG: ChangelogItem[] = [
  {
    id: 'tool-json-corruption',
    category: 'Fix',
    title: 'Tool Call Argument JSON Corruption & _raw Parameter Crash',
    severity: 'Critical',
    symptomInLogs: 'Error: InputValidationError: Write failed due to: The required parameter `file_path` is missing, `content` missing, unexpected `_raw` provided (Log Index 34 & 35).',
    rootCause: 'When Write or Bash emitted large multi-line payloads inside <arguments>...</arguments>, standard json.loads failed. The old code immediately fell back to {"_raw": raw_args}, causing downstream agent APIs to reject the call.',
    solution: 'Implemented safe_parse_tool_arguments() with multi-stage sanitization (newline normalization, unescaped quote recovery, and heuristic parameter extraction for file_path, content, command).',
    diffHighlight: {
      file: 'app4.py :: extract_local_tool_invocation',
      before: `raw_args = match.group(2).strip()
try:
    args = json.loads(raw_args) if raw_args else {}
except json.JSONDecodeError:
    args = {"_raw": raw_args}  # ❌ Fails on downstream schema validation!`,
      after: `tool_name = match.group(1).strip()
raw_args = match.group(2).strip()
# ✅ Multi-stage JSON repair & heuristic parameter extraction
args = safe_parse_tool_arguments(raw_args, tool_name=tool_name)`
    }
  },
  {
    id: 'history-bloat-504',
    category: 'Performance',
    title: 'Exponential History Bloat & 502/504 Gateway Timeouts',
    severity: 'Critical',
    symptomInLogs: 'Turn 17: 42KB -> Turn 21: 84KB -> Turn 25: 132KB -> 504 Gateway Timeout and 502 Bad Gateway from Nginx (Log 18:48:38).',
    rootCause: 'extract_tool_execution_context iterated every message from index 0, concatenating all previous tool results over and over on every turn, causing prompts to exceed 135,000 characters.',
    solution: 'Replaced with extract_last_tool_execution_context() which scans backward from the end of the history to isolate ONLY the trailing tool results for the immediate turn.',
    diffHighlight: {
      file: 'app4.py :: extract_last_tool_execution_context',
      before: `def extract_tool_execution_context(messages: List[Dict[str, Any]]) -> str:
    formatted_blocks = []
    for msg in messages:  # ❌ Re-sends all 30+ historic tool outputs!
        if role in {"tool", "function"}: ...`,
      after: `def extract_last_tool_execution_context(messages: List[Dict[str, Any]]) -> str:
    # ✅ Scans backwards from the end to gather ONLY trailing round
    idx = len(messages) - 1
    while idx >= 0 and messages[idx].get("role") in {"tool", "function"}:
        ...`
    }
  },
  {
    id: 'system-reminder-pollution',
    category: 'Sanitization',
    title: 'Synthetic Reminder & Interruption Tag Stripping',
    severity: 'Medium',
    symptomInLogs: '<system-reminder>snip_id=...; system-generated; do not discuss...</system-reminder> and [Request interrupted by user] leaked into detector prompts.',
    rootCause: 'The code took user messages verbatim from reversed message history, polluting the mode detector instructions with agent framework meta-prompts.',
    solution: 'Added clean_user_message() to scrub XML system tags, snip IDs, and task tracking reminders before persona mode routing.',
    diffHighlight: {
      file: 'app4.py :: clean_user_message',
      before: `user_query = str(m.get("content", ""))  # ❌ Included raw <system-reminder> tags!`,
      after: `def clean_user_message(content: Any) -> str:
    text = ...
    text = re.sub(r"<system-reminder>.*?</system-reminder>", "", text, flags=re.DOTALL)
    text = re.sub(r"\\[Request interrupted by user\\]", "", text)
    return text.strip()  # ✅ Clean conversational prompt`
    }
  },
  {
    id: 'network-resilience-retries',
    category: 'Resilience',
    title: 'Resilient HTTP Layer with Exponential Backoff Retries',
    severity: 'High',
    symptomInLogs: 'DNS resolution drops (Errno -2) and transient 502 Bad Gateway errors aborted streaming sessions immediately without retry.',
    rootCause: 'Standard requests.Session() made single raw HTTP attempts without retrying transient 502/503/504 status codes.',
    solution: 'Mounted HTTPAdapter with urllib3 Retry policy (3 attempts, backoff factor 1.5) on both HTTPS and HTTP pools.',
    diffHighlight: {
      file: 'app4.py :: DanswerClient.__init__',
      before: `self.session = requests.Session()  # ❌ No retry adapter`,
      after: `retries = Retry(
    total=3,
    backoff_factor=1.5,
    status_forcelist=[502, 503, 504],
    raise_on_status=False,
)
self.session.mount("https://", HTTPAdapter(max_retries=retries))`
    }
  },
  {
    id: 'detector-leak-prevention',
    category: 'Resilience',
    title: 'Leak-Proof Detector & Segment Memory Cleanup',
    severity: 'Medium',
    symptomInLogs: 'Failed to reset detector session session_id=...: Onyx API error 502.',
    rootCause: 'If the remote DELETE call failed, an exception was raised before removing the session from local memory, keeping dead session IDs active.',
    solution: 'Guaranteed local dictionary purging via pop(..., None) inside a lock before initiating network teardown.',
    diffHighlight: {
      file: 'app4.py :: ConversationStore.reset_detector_session',
      before: `def reset_detector_session(self, conversation_id: str) -> None:
    with self._lock:
        session_id = self._detector_sessions.pop(conversation_id, None)
        if session_id:
            self.client.delete_chat_session(session_id) # ❌ Throws & leaves lock state inconsistent`,
      after: `def reset_detector_session(self, conversation_id: str) -> None:
    with self._lock:
        session_id = self._detector_sessions.pop(conversation_id, None)
    if session_id:
        try:
            self.client.delete_chat_session(session_id, kind="detector_reset")
        except Exception as e:
            logger.warning("Failed to delete remote detector session: %s", e)  # ✅ Safe fallback`
    }
  },
  {
    id: 'xml-hallucination-instructions',
    category: 'Sanitization',
    title: 'Streaming XML Prompt Hardening against Fake Results',
    severity: 'High',
    symptomInLogs: 'Assistant generated fake ls directory listings with (waiting for result...) inside its own output before receiving tool returns.',
    rootCause: 'System tool prompt lacked explicit constraints forbidding the LLM from outputting speculative tool execution mockups.',
    solution: 'Added explicit critical negative constraints to format_external_tools_for_danswer forbidding simulated tool results.',
    diffHighlight: {
      file: 'app4.py :: Orchestrator.format_external_tools_for_danswer',
      before: `"You have access to local tools. When invoking a tool, emit an XML call..."`,
      after: `"CRITICAL INSTRUCTIONS:\\n"
"1. The <arguments> block MUST contain valid escaped JSON.\\n"
"2. Do NOT output fake/hallucinated results before receiving actual tool output.\\n"
"3. Do NOT include extraneous markdown inside the <local_tool> tag."`
    }
  },
  {
    id: 'openai-models-endpoint',
    category: 'Resilience',
    title: 'OpenAI /v1/models Discovery Handshake Endpoint',
    severity: 'Medium',
    symptomInLogs: 'GET /v1/models returned 404 Not Found when Claude CLI or client probes available models.',
    rootCause: 'Missing @app.route("/v1/models") endpoint required by OpenAI-compatible client libraries during session startup.',
    solution: 'Added /v1/models route returning full manifest of persona models and recognized aliases (e.g. any, gpt-4o, claude-3-7-sonnet).',
    diffHighlight: {
      file: 'app4.py :: @app.route("/v1/models")',
      before: `(No route handler for /v1/models -> Flask 404 Not Found)`,
      after: `@app.route("/v1/models", methods=["GET"])
def list_models():
    return Response(json.dumps({"object": "list", "data": model_entries}), mimetype="application/json")`
    }
  },
  {
    id: 'upstream-error-visibility',
    category: 'Resilience',
    title: 'Visible Danswer Upstream & Connection Error Reporting',
    severity: 'High',
    symptomInLogs: 'When Danswer was inaccessible or returned network errors, the proxy yielded silent blank stream chunks that appeared to the user as an empty message.',
    rootCause: 'Streaming exception handler swallowed upstream errors with a generic empty close instead of outputting an explicit diagnostic message chunk to the client.',
    solution: 'Enriched exception handlers to emit [Danswer / Upstream Error: <details>] directly in the event stream before [DONE], exposing network issues immediately.',
    diffHighlight: {
      file: 'app4.py :: generate_sse()',
      before: `except Exception as exc:
    logger.exception("Streaming request failed")
    yield f"data: {json.dumps(error_chunk)}\\n\\n"
    yield "data: [DONE]\\n\\n"`,
      after: `except Exception as exc:
    logger.exception("Streaming request failed due to upstream Danswer error: %s", exc)
    error_msg = f"\\n\\n[Danswer / Upstream Error: {exc}]\\n"
    yield f"data: {json.dumps(make_completion_chunk(completion_id=completion_id, content=error_msg, finish_reason='stop'))}\\n\\n"
    yield "data: [DONE]\\n\\n"`
    }
  },
  {
    id: 'title-generator-fast-path',
    category: 'Concurrency',
    title: 'Local Fast-Path for Background Title Generator',
    severity: 'Critical',
    symptomInLogs: 'Greetings ("hello") were swallowed by Claude CLI background requests and parallel title requests collided with the main terminal chat session in Onyx.',
    rootCause: 'Claude CLI issues a background request with system prompt "Generate a concise, sentence-case title" to name the tab in ~/.claude/sessions/. Forwarding it to Danswer tied up the single chat session and hid the AI response from the terminal.',
    solution: 'Fast-pathed title generation requests locally with an immediate synthetic JSON payload ({"title": "..."}), bypassing Danswer and eliminating session race conditions completely.',
    diffHighlight: {
      file: 'app4.py :: chat_completions()',
      before: `(Forwarded all background title requests directly to Danswer, locking the active chat session)`,
      after: `if "Generate a concise, sentence-case title" in first_system_msg:
    title_json = json.dumps({"title": title_text})
    return Response(json.dumps({"choices": [{"message": {"content": title_json}}]}), mimetype="application/json")`
    }
  },
  {
    id: 'anti-hallucination-cwd-guard',
    category: 'Tooling & Execution',
    title: 'CWD Injection, Anti-Hallucination & Dummy Tool Filtering',
    severity: 'High',
    symptomInLogs: 'Model hallucinated fake directory contents (`total 8`) before calling `ls -la`, guessed `/home/janis/app5.py` instead of `/home/janis/DANSWER/app5.py`, and emitted phantom `TOOL_NAME` calls at the end of responses.',
    rootCause: 'Lack of CWD in the system prompt caused path guessing, weak preemption allowed fake pre-tool text generation, and verbatim template examples caused regurgitation of `TOOL_NAME`.',
    solution: 'Injected `os.getcwd()` into the system prompt, added strict preemption directives ("stop generating after </local_tool>"), and filtered out dummy placeholder names in the parser.',
    diffHighlight: {
      file: 'app4.py :: format_external_tools_for_danswer()',
      before: `You have access to local tools... <name>TOOL_NAME</name>`,
      after: `CURRENT LOCAL WORKING DIRECTORY: {os.getcwd()}
1. DO NOT guess, simulate, hallucinate directory contents or code.
2. Emit <local_tool> IMMEDIATELY. STOP generating after </local_tool>.`
    }
  }
];

export const LOG_SAMPLES = [
  {
    turn: 34,
    time: '18:54:50',
    type: 'ERROR',
    issue: 'JSON Parse Failure & _raw parameter rejection',
    details: 'Tool `Write` called with broken escaped string -> Agent CLI responded with InputValidationError (missing file_path, missing content).'
  },
  {
    turn: 25,
    time: '18:48:38',
    type: 'TIMEOUT',
    issue: 'Nginx 504 Gateway Timeout & 502 Bad Gateway',
    details: 'Prompt length reached 132,528 characters due to historic tool duplication -> Danswer upstream timed out after 60s.'
  },
  {
    turn: 23,
    time: '18:47:31',
    type: 'NETWORK',
    issue: 'DNS Resolution Error (Errno -2)',
    details: 'Failed to resolve danswer.irpc.int.tietoevry.com during detector route check.'
  },
  {
    turn: 6,
    time: '18:44:31',
    type: 'HALLUCINATION',
    issue: 'Speculative Tool Output Leakage',
    details: 'Assistant hallucinated `total 8 drwxr-x` directory listing inline while emitting tool call XML.'
  }
];
