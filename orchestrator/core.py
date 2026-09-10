"""
Core Orchestration engine managing persona handovers, tool interception, and multi-turn loops.
"""

import json
import os
from typing import Any, Dict, Iterator, List, Optional, Tuple

from orchestrator.client import DanswerClient
from orchestrator.config import (
    PERSONAS,
    PRIMARY_PERSONA_ID,
    REAL_TALK_MODEL,
    ROUTING_MODEL,
    get_run_logger,
    logger,
)
from orchestrator.models import DescriptorStatus, Segment
from orchestrator.session_store import ConversationStore
from orchestrator.tool_parser import (
    clean_user_message,
    extract_last_tool_execution_context,
)
from orchestrator.workspace_sync import WorkspaceProjectSync


class Orchestrator:
    def format_external_tools_for_danswer(
        self, tools: Optional[List[dict]], workspace_sync: Optional[Any] = None
    ) -> str:
        if not tools:
            return ""

        sync = workspace_sync or getattr(self, "workspace_sync", None)
        cwd = sync.root if (sync and hasattr(sync, "root")) else os.getcwd()
        lines = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            fn = tool.get("function", tool)
            if isinstance(fn, dict) and fn.get("name"):
                desc = fn.get("description", "")
                params = json.dumps(fn.get("parameters", {}))
                lines.append(f"- Tool: {fn['name']}\n  Description: {desc}\n  Parameters schema: {params}")

        if not lines:
            return ""

        return (
            "\n\n[SYSTEM INSTRUCTION: LOCAL TOOL EXECUTION INTERFACE]\n"
            f"CURRENT LOCAL WORKING DIRECTORY: {cwd}\n\n"
            "You have access to real local filesystem and terminal tools on the user's system.\n"
            "When the user requests inspecting files, listing directories, reading code, or running shell commands:\n"
            "1. DO NOT guess, simulate, hallucinate, or pretend what the directory contents or file lines are.\n"
            "2. DO NOT output fake ls output, fake directory trees, or imaginary code blocks before the tool executes.\n"
            "3. Emit the <local_tool> tag IMMEDIATELY with at most a brief 1-sentence explanation.\n"
            "4. STOP generating immediately after </local_tool>. You will receive the real execution results on the next turn to provide your full answer.\n"
            "5. For file paths, use relative paths (e.g. 'app5.py') or paths rooted in CURRENT LOCAL WORKING DIRECTORY.\n"
            "6. Do NOT output <local_tool> tags or example templates in your final answer when no tool execution is required.\n\n"
            "TOOL INVOCATION XML SYNTAX:\n"
            "<local_tool>\n"
            "  <name>actual_tool_name</name>\n"
            "  <arguments>{\"param_key\": \"param_value\"}</arguments>\n"
            "</local_tool>\n\n"
            "Available tools on user system:\n" + "\n".join(lines)
        )

    def __init__(
        self,
        client: DanswerClient,
        routing_manifest: str,
        tool_ids: List[int],
        workspace_sync: Optional[WorkspaceProjectSync] = None,
    ):
        self.client = client
        self.routing_manifest = routing_manifest
        self.tool_ids = tool_ids
        self.workspace_sync = workspace_sync
        self.sessions = ConversationStore(client=client)

    def complete_non_streaming(
        self, session_id: str, message: str, temperature: float, model: str, disable_search: bool = False
    ) -> str:
        response = self.client.send_message(
            session_id=session_id,
            message=message,
            stream=False,
            temperature=temperature,
            allowed_tool_ids=self.tool_ids,
            model=model,
            disable_search=disable_search,
        )
        return self.client.extract_complete_answer(response)

    def detect_mode(
        self, conversation_id: str, current_persona_id: int, current_message: str
    ) -> Tuple[str, int, str]:
        current_name = PERSONAS.get(current_persona_id, f"Persona {current_persona_id}")

        prompt_and_message = f"""
[SYSTEM INSTRUCTION - MODE DETECTOR]
YOU ARE AN AUTOMATED ROUTING COMPONENT. YOU MUST NEVER RESPOND TO THE USER DIRECTLY OR ANSWER THEIR QUESTIONS.
YOUR ONLY ALLOWED OUTPUT IS A SINGLE CLASSIFICATION LINE.

CURRENT ACTIVE PERSONA: ID={current_persona_id} ({current_name})

ROUTING MANIFEST:
{self.routing_manifest}

INSTRUCTIONS:
Classify the user message below. Decide if it continues the current conversational mode or requires switching personas.
You MUST respond with EXACTLY one line in this format (no conversational greeting, no markdown formatting, no explanations, no chat response):
CONTINUE|{current_persona_id}|<brief_reason>
or
SWITCH|<target_persona_id>|<brief_reason>

CRITICAL: DO NOT ANSWER THE USER MESSAGE. DO NOT ATTEMPT TO SOLVE THEIR PROBLEM. ONLY CLASSIFY AND ROUTE.

--- USER MESSAGE FOR CLASSIFICATION ---
{current_message}
--- END USER MESSAGE ---

REMINDER: YOUR OUTPUT MUST BE A SINGLE LINE STARTING WITH 'CONTINUE|' OR 'SWITCH|'.
""".strip()

        detector_session = self.sessions.get_or_create_detector_session(conversation_id)

        try:
            answer = self.complete_non_streaming(
                session_id=detector_session,
                message=prompt_and_message,
                temperature=0.0,
                model=ROUTING_MODEL,
                disable_search=True,
            ).strip()
        except Exception as exc:
            logger.error(
                "Detector call failed on conversation_id=%s due to upstream Onyx/Danswer error: %s",
                conversation_id,
                exc,
            )
            self.sessions.reset_detector_session(conversation_id)
            return "CONTINUE", current_persona_id, f"detector error: {exc}"

        line = answer.splitlines()[0].strip() if answer else ""
        parts = line.split("|", 2)

        if len(parts) != 3 or parts[0].upper() not in {"CONTINUE", "SWITCH"}:
            logger.warning("Invalid detector response ('%s'). Resetting detector session.", answer)
            self.sessions.reset_detector_session(conversation_id)
            return "CONTINUE", current_persona_id, "invalid detector format"

        decision, target_p, reason = parts[0].strip().upper(), parts[1].strip(), parts[2].strip()
        try:
            persona_id = int(target_p)
        except ValueError:
            return "CONTINUE", current_persona_id, "invalid persona id"

        if persona_id not in PERSONAS:
            return "CONTINUE", current_persona_id, "invalid target persona"

        target_p_id = persona_id if decision == "SWITCH" else current_persona_id
        get_run_logger().log_llm_response(
            model=ROUTING_MODEL,
            session_id=detector_session,
            response_summary=f"decision={decision} target={target_p_id} reason={reason}",
            extra={"decision": decision, "target_persona": target_p_id, "reason": reason},
        )

        return decision, target_p_id, reason

    def compact_segment(self, segment: Segment) -> str:
        prompt = (
            "Please summarize the key decisions, context, and output from our conversation so far "
            "into a concise handover summary for another specialist."
        )

        result = self.complete_non_streaming(
            session_id=segment.session_id,
            message=prompt,
            temperature=0.0,
            model=REAL_TALK_MODEL,
            disable_search=True,
        ).strip()

        get_run_logger().log_llm_response(
            model=REAL_TALK_MODEL,
            session_id=segment.session_id,
            response_summary=result,
            extra={"action": "COMPACT_SEGMENT", "persona_id": segment.persona_id},
        )

        return result

    def get_or_create_initial_segment(self, conversation_id: str) -> Segment:
        active = self.sessions.get_active(conversation_id)
        if active is not None:
            return active

        project_id = self.workspace_sync.project_id if self.workspace_sync else None
        return self.sessions.create_segment(
            conversation_id=conversation_id,
            persona_id=PRIMARY_PERSONA_ID,
            project_id=project_id,
        )

    def process_query(
        self,
        conversation_id: str,
        messages: List[Dict[str, Any]],
        external_tools: Optional[List[dict]] = None,
    ) -> Iterator[str]:
        if self.workspace_sync:
            self.workspace_sync.check_and_refresh_watched_files()

        active = self.get_or_create_initial_segment(conversation_id)

        user_query = ""
        for m in reversed(messages):
            if isinstance(m, dict) and m.get("role") == "user":
                raw_content = m.get("content", "")
                user_query = clean_user_message(raw_content)
                logger.info("DEBUG: raw_user_content_length=%s, clean_user_query=%r", len(str(raw_content)), user_query)
                if user_query:
                    break

        decision, target_persona, reason = self.detect_mode(
            conversation_id=conversation_id,
            current_persona_id=active.persona_id,
            current_message=user_query or "(tool execution step)",
        )

        persona_switched = False
        old_persona_name = PERSONAS.get(active.persona_id, f"Persona {active.persona_id}")

        if decision == "SWITCH" and target_persona != active.persona_id:
            compaction = self.compact_segment(active)
            self.sessions.close_active(conversation_id=conversation_id, compaction=compaction)
            inherited = self.sessions.inherited_context(conversation_id)

            project_id = self.workspace_sync.project_id if self.workspace_sync else None
            active = self.sessions.create_segment(
                conversation_id=conversation_id,
                persona_id=target_persona,
                project_id=project_id,
                inherited_context=inherited,
            )
            persona_switched = True

        system_notice = ""
        if persona_switched:
            new_persona_name = PERSONAS.get(target_persona, f"Persona {target_persona}")
            system_notice = f"*[Switched persona from {old_persona_name} to {new_persona_name}]*\n\n"
            get_run_logger().log_action(
                category="PERSONA",
                action="SWITCH",
                details={
                    "conversation_id": conversation_id,
                    "from_persona": old_persona_name,
                    "to_persona": new_persona_name,
                    "reason": reason,
                },
            )
            yield system_notice

        tool_context = extract_last_tool_execution_context(messages, workspace_sync=self.workspace_sync)
        workspace_header = self.workspace_sync.get_system_context_header() if self.workspace_sync else ""

        if persona_switched and active.inherited_context:
            base_message = (
                f"{workspace_header}\n\n" if workspace_header else ""
            ) + (
                f"INHERITED CONTEXT:\n{active.inherited_context}\n\n"
                f"{tool_context}"
                f"USER MESSAGE:\n{user_query}"
            )
        else:
            merged_tools_and_query = f"{tool_context}{user_query}" if tool_context else user_query
            base_message = f"{workspace_header}\n\n{merged_tools_and_query}" if workspace_header else merged_tools_and_query

        tool_inventory_appendix = self.format_external_tools_for_danswer(external_tools)
        message_for_persona = f"{base_message}\n{tool_inventory_appendix}" if tool_inventory_appendix else base_message

        if user_query:
            self.sessions.append_message(conversation_id=conversation_id, role="user", content=user_query)

        chunks: List[str] = []
        if persona_switched and system_notice:
            chunks.append(system_notice)

        current_message_to_send = message_for_persona
        redispatch_count = 0
        max_redispatches = 3

        try:
            while redispatch_count <= max_redispatches:
                # Only pull descriptors that have reached READY state via on_attach_complete callback
                file_descriptors = self.workspace_sync.get_ready_descriptors() if self.workspace_sync else []

                try:
                    response = self.client.send_message(
                        session_id=active.session_id,
                        message=current_message_to_send,
                        stream=True,
                        temperature=0.3,
                        allowed_tool_ids=self.tool_ids,
                        file_descriptors=file_descriptors,
                        model=REAL_TALK_MODEL,
                    )

                    buffered_output = ""
                    intercepted_batch = False
                    streamed_anything = False
                    turn_chunks: List[str] = []

                    for chunk in self.client.iter_stream_text(response):
                        buffered_output += chunk
                        turn_chunks.append(chunk)

                        # Check for tool call intercept opportunity before streaming to client
                        if "<local_tool>" in buffered_output and "</local_tool>" in buffered_output and not streamed_anything and self.workspace_sync and redispatch_count < max_redispatches:
                            all_tools = DanswerClient.extract_all_local_tool_invocations(buffered_output)
                            if all_tools:
                                # Detect if any read/grounding tool is present in the invocation batch
                                has_read_tool = False
                                for t in all_tools:
                                    t_name = (t.get("name") or "").lower().strip()
                                    t_args = t.get("arguments") or {}
                                    t_fp = t_args.get("file_path") or t_args.get("path")
                                    if t_name in {"read_file", "read", "view", "cat", "view_file"} or (t_fp and t_name not in {"list_dir", "ls", "dir", "grep_search", "grep", "search_code"}):
                                        has_read_tool = True
                                        break

                                if has_read_tool:
                                    intercepted_batch = True
                                    logger.info("[AUTO-GROUNDING INTERCEPT] Intercepted batch of %d tool call(s) containing read/grounding tool.", len(all_tools))
                                    get_run_logger().log_tool_call(
                                        tool_name="[AUTO_GROUNDING_BATCH]",
                                        arguments={"tool_count": len(all_tools)},
                                        result_summary="Intercepted read tools for blocking workspace sync",
                                        intercepted=True,
                                    )

                                    attached_headers: List[str] = []
                                    tool_result_entries: List[str] = []

                                    for t in all_tools:
                                        t_name = (t.get("name") or "").lower().strip()
                                        t_args = t.get("arguments") or {}
                                        t_fp = t_args.get("file_path") or t_args.get("path")
                                        is_read = t_name in {"read_file", "read", "view", "cat", "view_file"} or (t_fp and t_name not in {"list_dir", "ls", "dir", "grep_search", "grep", "search_code"})

                                        if is_read and t_fp:
                                            logger.info("[AUTO-GROUNDING SYNC] Blocking sync for file: '%s'", t_fp)
                                            desc = self.workspace_sync.upload_and_attach_blocking(t_fp)
                                            canonical = desc.canonical_name if (desc and desc.canonical_name) else self.workspace_sync.canonical_name(t_fp, is_dir=False)
                                            if desc and desc.status == DescriptorStatus.READY:
                                                attached_headers.append(f"FILE {t_fp} was attached as {canonical}")
                                                tool_result_entries.append(f"- Tool '{t.get('name')}' ({t_fp}): Attached and indexed in project context as {canonical}.")
                                            else:
                                                tool_result_entries.append(f"- Tool '{t.get('name')}' ({t_fp}): Failed to sync file to project.")
                                        else:
                                            # Execute local non-read tool against workspace disk
                                            res_output = self.workspace_sync.execute_local_non_read_tool(t.get("name", ""), t_args)
                                            logger.info("[AUTO-GROUNDING LOCAL TOOL] Executed non-read tool '%s': %s", t.get("name"), res_output[:120])
                                            tool_result_entries.append(f"- Tool '{t.get('name')}' output:\n{res_output}")

                                    # Construct prompt with file attachments, real tool results, and original query
                                    prompt_sections = []
                                    if attached_headers:
                                        prompt_sections.append("\n".join(attached_headers))
                                    if tool_result_entries:
                                        prompt_sections.append("[LOCAL TOOL EXECUTION RESULTS]:\n" + "\n\n".join(tool_result_entries))
                                    prompt_sections.append(f"[ORIGINAL REQUEST]:\n{message_for_persona}")

                                    current_message_to_send = "\n\n".join(prompt_sections)
                                    redispatch_count += 1
                                    break

                        # If we might be receiving a tool call, buffer chunks without yielding until </local_tool> or non-tool text
                        is_tool_call_prefix = (len(buffered_output) < 12 and "<local_tool>".startswith(buffered_output)) or ("<local_tool>" in buffered_output)
                        if not streamed_anything and is_tool_call_prefix and "</local_tool>" not in buffered_output and self.workspace_sync and redispatch_count < max_redispatches:
                            continue

                        for c in turn_chunks:
                            yield c
                        turn_chunks = []
                        streamed_anything = True

                    if not intercepted_batch:
                        chunks.extend(turn_chunks)
                        break

                except Exception as inner_exc:
                    exc_str = str(inner_exc)
                    if "not associated with project" in exc_str and self.workspace_sync and redispatch_count < max_redispatches:
                        logger.warning("Detected unassociated file error from Onyx: %s. Attempting re-attachment / invalidation...", inner_exc)
                        import re
                        file_ids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", exc_str, re.I)
                        for fid in file_ids:
                            for cname, desc in list(self.workspace_sync.descriptors.items()):
                                if desc.file_id == fid:
                                    logger.info("Attempting to re-attach unassociated file descriptor '%s' (file_id=%s) to project %s", cname, fid, desc.project_id)
                                    reattached = False
                                    if desc.project_id:
                                        try:
                                            reattached = self.client.attach_file_to_project(desc.project_id, fid)
                                        except Exception as reattach_err:
                                            logger.warning("Re-attach attempt failed for '%s': %s", cname, reattach_err)
                                    if reattached:
                                        logger.info("Re-attached unassociated file '%s' (file_id=%s) successfully.", cname, fid)
                                        desc.status = DescriptorStatus.READY
                                    else:
                                        logger.info("Invalidating unassociated file descriptor '%s' (file_id=%s)", cname, fid)
                                        desc.status = DescriptorStatus.FAILED
                                        desc.file_id = None
                                        if cname in self.workspace_sync.file_hashes:
                                            del self.workspace_sync.file_hashes[cname]
                        redispatch_count += 1
                        continue
                    raise inner_exc

        except Exception as exc:
            logger.error("Streaming message invocation failed: %s", exc)
            raise RuntimeError(f"Onyx invocation error: {exc}") from exc

        final_answer = "".join(chunks)
        self.sessions.append_message(conversation_id=conversation_id, role="assistant", content=final_answer)
        get_run_logger().log_llm_response(
            model=REAL_TALK_MODEL,
            session_id=active.session_id,
            response_summary=final_answer,
            extra={"conversation_id": conversation_id},
        )
