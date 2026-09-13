"""
Mock Onyx / Danswer server implementation for testing and local development.
Simulates Onyx REST API endpoints and SSE streaming.
"""

import argparse
import json
import time
import uuid
from typing import Any, Dict, List
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

# In-memory mock database state
STATE: Dict[str, Any] = {
    "personas": [
        {"id": 0, "name": "General Assistant", "description": "Default Onyx persona"},
        {"id": 1, "name": "Code Expert", "description": "Specialized coding assistant"},
    ],
    "tools": [
        {"id": 1, "name": "SearchTool", "description": "Internal document search"},
        {"id": 2, "name": "WebSearch", "description": "External web search"},
    ],
    "projects": [
        {"id": "proj-default", "name": "Default Workspace", "description": "Default workspace project"}
    ],
    "project_files": {
        "proj-default": [
            {"id": "file-1", "name": "README.md", "type": "plain_text"}
        ]
    },
    "chat_sessions": {},
    "uploaded_files": {},
    "file_contents": {},
    "project_instructions": {},
}


def reset_mock_state():
    """Reset mock state to defaults."""
    STATE["personas"] = [
        {"id": 0, "name": "General Assistant", "description": "Default Onyx persona"},
        {"id": 1, "name": "Code Expert", "description": "Specialized coding assistant"},
    ]
    STATE["tools"] = [
        {"id": 1, "name": "SearchTool", "description": "Internal document search"},
        {"id": 2, "name": "WebSearch", "description": "External web search"},
    ]
    STATE["projects"] = [
        {"id": "proj-default", "name": "Default Workspace", "description": "Default workspace project"}
    ]
    STATE["project_files"] = {
        "proj-default": [
            {"id": "file-1", "name": "README.md", "type": "plain_text"}
        ]
    }
    STATE["chat_sessions"] = {}
    STATE["uploaded_files"] = {}
    STATE["file_contents"] = {}
    STATE["project_instructions"] = {}


@app.route("/api/me/permissions", methods=["GET"])
def me_permissions():
    """Return user/token permissions according to Onyx API spec."""
    return jsonify({
        "permissions": ["basic", "read:chat", "write:chat", "read:search", "manage:connectors"],
        "is_manager": False,
        "managed_group_ids": [],
    })


@app.route("/api/persona", methods=["GET"])
def get_personas():
    """Return list of available personas."""
    return jsonify(STATE["personas"])


@app.route("/api/tool", methods=["GET"])
def get_tools():
    """Return list of available tools."""
    return jsonify(STATE["tools"])


@app.route("/api/chat/get-user-chat-sessions", methods=["GET"])
def get_user_chat_sessions():
    """Return user chat sessions."""
    sessions = list(STATE["chat_sessions"].values())
    return jsonify({"sessions": sessions})


@app.route("/api/user/projects", methods=["GET"])
@app.route("/api/user/projects/", methods=["GET"])
def get_user_projects():
    """Return user projects."""
    return jsonify({"projects": STATE["projects"]})


@app.route("/api/user/files/recent", methods=["GET"])
def get_recent_files():
    """Return recently uploaded user files with status COMPLETED."""
    recent = []
    for fid, fdict in STATE["uploaded_files"].items():
        recent.append({
            "id": fid,
            "file_id": fid,
            "name": fdict.get("name", "file.txt"),
            "file_type": fdict.get("type", "plain_text"),
            "status": "COMPLETED",
        })
    return jsonify(recent)


@app.route("/api/user/projects/file/<file_id>", methods=["GET"])
def get_user_file_snapshot(file_id: str):
    """Return a UserFileSnapshot for status polling."""
    fdict = STATE["uploaded_files"].get(file_id)
    if not fdict:
        return jsonify({"detail": "File not found"}), 404
    return jsonify({
        "id": file_id,
        "file_id": file_id,
        "name": fdict.get("name", "file.txt"),
        "file_type": fdict.get("type", "plain_text"),
        "chat_file_type": "plain_text",
        "status": "COMPLETED",
        "project_id": None,
    })


@app.route("/api/user/projects/<project_id>/instructions", methods=["GET", "POST"])
def project_instructions(project_id: str):
    """Get or upsert project instructions."""
    if request.method == "GET":
        return jsonify({"instructions": STATE["project_instructions"].get(project_id)})
    data = request.get_json(silent=True) or {}
    STATE["project_instructions"][project_id] = data.get("instructions", "")
    return jsonify({"instructions": STATE["project_instructions"][project_id]})


@app.route("/api/chat/file/<file_id>", methods=["GET"])
def get_file_blob(file_id: str):
    """Return the stored blob content of an uploaded file."""
    content = STATE["file_contents"].get(file_id)
    if content is None:
        return jsonify({"detail": "File not found"}), 404
    return Response(content, mimetype="text/plain")


@app.route("/api/user/projects/files/<project_id>", methods=["GET"])
def get_project_files(project_id: str):
    """Return files associated with a project."""
    files = STATE["project_files"].get(project_id, [])
    return jsonify({"files": files})


@app.route("/api/user/projects/create", methods=["POST"])
def create_project():
    """Create a new user project."""
    data = request.get_json(silent=True) or {}
    name = data.get("name") or request.args.get("name") or "New Project"
    description = data.get("description") or request.args.get("description") or ""

    proj_id = f"proj-{uuid.uuid4().hex[:8]}"
    project = {"id": proj_id, "name": name, "description": description}

    STATE["projects"].append(project)
    STATE["project_files"][proj_id] = []

    return jsonify(project), 200


@app.route("/api/user/projects/file/upload", methods=["POST"])
def upload_project_file():
    """Upload a file to project."""
    project_id = request.form.get("project_id", "")
    file_obj = request.files.get("files") or request.files.get("file")

    file_id = f"file-{uuid.uuid4().hex[:8]}"
    filename = file_obj.filename if file_obj else "file.txt"
    content_bytes = file_obj.read() if file_obj else b""

    file_descriptor = {
        "id": file_id,
        "file_id": file_id,
        "name": filename,
        "type": "plain_text",
        "chat_file_type": "plain_text",
        "status": "COMPLETED",
    }

    STATE["uploaded_files"][file_id] = file_descriptor
    try:
        STATE["file_contents"][file_id] = content_bytes.decode("utf-8", errors="replace")
    except Exception:
        STATE["file_contents"][file_id] = ""

    if project_id:
        if project_id not in STATE["project_files"]:
            STATE["project_files"][project_id] = []
        STATE["project_files"][project_id].append(file_descriptor)

    return jsonify({
        "user_files": [file_descriptor],
        "file_descriptor": file_descriptor,
        "rejected_files": [],
    }), 200


@app.route("/api/user/projects/<project_id>/files/<file_id>", methods=["POST"])
@app.route("/api/user/projects/<project_id>/file/<file_id>", methods=["POST"])
@app.route("/api/user/projects/<project_id>/files", methods=["POST"])
def attach_file_to_project(project_id: str, file_id: str = None):
    """Link uploaded file(s) to project."""
    if project_id not in STATE["project_files"]:
        STATE["project_files"][project_id] = []

    data = request.get_json(silent=True) or {}
    fids = []
    if file_id:
        fids.append(file_id)
    if "file_ids" in data and isinstance(data["file_ids"], list):
        fids.extend(data["file_ids"])
    if "file_id" in data and data["file_id"] and data["file_id"] not in fids:
        fids.append(data["file_id"])

    for fid in fids:
        descriptor = STATE["uploaded_files"].get(fid) or {
            "id": fid,
            "name": f"file-{fid}",
            "type": "plain_text",
        }
        if not any(f["id"] == fid for f in STATE["project_files"][project_id]):
            STATE["project_files"][project_id].append(descriptor)

    return jsonify({"success": True}), 200


@app.route("/api/user/projects/file/<file_id>", methods=["DELETE"])
@app.route("/api/user/projects/<project_id>/files/<file_id>", methods=["DELETE"])
def delete_project_file(file_id: str, project_id: str = ""):
    """Delete project file."""
    if file_id in STATE["uploaded_files"]:
        del STATE["uploaded_files"][file_id]

    for p_id, files in STATE["project_files"].items():
        STATE["project_files"][p_id] = [f for f in files if f.get("id") != file_id]

    return "", 204


@app.route("/api/chat/create-chat-session", methods=["POST"])
def create_chat_session():
    """Create a new Onyx chat session."""
    data = request.get_json(silent=True) or {}
    persona_id = data.get("persona_id", 0)
    description = data.get("description", "Mock Session")
    project_id = data.get("project_id")

    session_id = str(uuid.uuid4())
    session_data = {
        "chat_session_id": session_id,
        "id": session_id,
        "persona_id": persona_id,
        "description": description,
        "chat_session_name": description,
        "project_id": project_id,
    }

    STATE["chat_sessions"][session_id] = session_data
    return jsonify(session_data), 200


@app.route("/api/chat/delete-chat-session/<session_id>", methods=["DELETE"])
def delete_chat_session(session_id: str):
    """Delete a chat session."""
    if session_id in STATE["chat_sessions"]:
        del STATE["chat_sessions"][session_id]
    return "", 200


@app.route("/api/chat/session-history/<session_id>", methods=["GET"])
def get_session_history(session_id: str):
    """Return stored chat history for a mock session."""
    session = STATE["chat_sessions"].get(session_id)
    if not session:
        return jsonify({"error": "Session not found"}), 404
    return jsonify({"history": session.get("history", [])}), 200


@app.route("/api/chat/send-chat-message", methods=["POST"])
def send_chat_message():
    """Send a chat message to Onyx (supports JSON & SSE streaming)."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    stream = data.get("stream", False)
    session_id = data.get("chat_session_id")
    file_descriptors = data.get("file_descriptors", [])
    chunk_delay = float(data.get("chunk_delay", 0.0) or request.args.get("chunk_delay", 0.0) or 0.0)

    # Record user message in session history if session exists
    if session_id and session_id in STATE["chat_sessions"]:
        if "history" not in STATE["chat_sessions"][session_id]:
            STATE["chat_sessions"][session_id]["history"] = []
        STATE["chat_sessions"][session_id]["history"].append({
            "role": "user",
            "content": message,
            "file_descriptors": file_descriptors,
        })

    # Handle Mode Detector classifier call
    if "[SYSTEM INSTRUCTION - MODE DETECTOR]" in message:
        detector_reply = "CONTINUE|0|Mock mode classifier decision"
        if stream:
            def generate_detector_sse():
                yield f"data: {json.dumps({'answer_piece': detector_reply})}\n\n"
                yield "data: [DONE]\n\n"
            return Response(generate_detector_sse(), mimetype="text/event-stream")
        return jsonify({
            "chat_session_id": session_id,
            "answer": detector_reply,
            "answer_citationless": detector_reply,
        }), 200

    # Extract actual clean user query text
    user_actual_text = message
    if "--- USER MESSAGE FOR CLASSIFICATION ---" in user_actual_text:
        user_actual_text = user_actual_text.split("--- USER MESSAGE FOR CLASSIFICATION ---")[1].split("--- END USER MESSAGE ---")[0]
    elif "USER MESSAGE:" in user_actual_text:
        user_actual_text = user_actual_text.split("USER MESSAGE:")[-1]
    elif "</workspace_context>" in user_actual_text:
        user_actual_text = user_actual_text.split("</workspace_context>")[-1]

    if "[SYSTEM INSTRUCTION" in user_actual_text:
        user_actual_text = user_actual_text.split("[SYSTEM INSTRUCTION")[0]

    user_actual_text = user_actual_text.strip()

    # Never echo <local_tool> syntax back (the proxy would execute echoed
    # example/placeholder tags as real tool calls).
    import re as _re_tag
    user_actual_text = _re_tag.sub(r"<local_tool>.*?</local_tool>", "", user_actual_text, flags=_re_tag.S).strip()

    # Project files are natively visible to sessions created with a project_id
    # (default persona + project). Mirrors Onyx resolve_context_user_files.
    session = STATE["chat_sessions"].get(session_id) or {}
    project_id = session.get("project_id")
    project_file_names = [
        f.get("name", "") for f in STATE["project_files"].get(project_id, [])
    ] if project_id else []

    # Determine response text based on attached file descriptors or tool call triggers
    requested_file_attached = False
    target_path = "src/auth.py"
    lower_user = user_actual_text.lower()
    has_read_trigger = (
        "[TRIGGER_TOOL_READ_FILE]" in message
        or "read the file" in lower_user
        or "read file" in lower_user
    )

    import re as _re
    write_match = _re.search(r"\[TRIGGER_TOOL_WRITE_FILE:([^\]]+)\]", message)
    has_write_trigger = write_match is not None

    # Guard: when the proxy redispatches after executing local tools, return a
    # final answer instead of re-triggering tool calls (avoids loops).
    tool_results_returned = "[LOCAL TOOL EXECUTION RESULTS]" in message

    if has_read_trigger:
        for word in user_actual_text.split():
            clean_w = word.strip(" '\"\t\n,")
            if (clean_w.endswith(".py") or clean_w.endswith(".txt")) and not clean_w.startswith("["):
                target_path = clean_w
                break
        target_token = target_path.replace("/", "_").replace(".", "_")
        for fd in file_descriptors:
            fname = fd.get("name", "")
            if target_token in fname or target_path in fname:
                requested_file_attached = True
                break
        if not requested_file_attached:
            # Also visible via native project-file injection
            requested_file_attached = any(
                target_token in pname or target_path in pname
                for pname in project_file_names
            )

    if has_read_trigger and requested_file_attached:
        attached_info = []
        for fd in file_descriptors:
            fid = fd.get("id") or fd.get("file_id")
            fname = fd.get("name") or fid
            attached_info.append(f"{fname} ({fid})")
        listed = [a.split(" (")[0] for a in attached_info]
        attached_info.extend(n for n in project_file_names if n not in listed)
        files_str = ", ".join(attached_info)
        response_text = f"Mock Onyx answer to: {user_actual_text} [Attached files: {files_str}]"
    elif tool_results_returned:
        visible_files = ", ".join(project_file_names) or "none"
        response_text = f"Mock Onyx answer to: {user_actual_text} [tool executed successfully] [Project files: {visible_files}]"
    elif has_write_trigger:
        write_path = write_match.group(1).strip() if write_match else "updated_file.txt"
        response_text = (
            '<local_tool><name>write_file</name>'
            f'<arguments>{{"file_path": "{write_path}", "content": "[UPDATED_BY_MOCK_WORKSPACE]"}}</arguments></local_tool>'
        )
    elif has_read_trigger and not requested_file_attached:
        response_text = f'<local_tool><name>read_file</name><arguments>{{"file_path": "{target_path}"}}</arguments></local_tool>'
    elif file_descriptors or project_file_names:
        attached_info = []
        for fd in file_descriptors:
            fid = fd.get("id") or fd.get("file_id")
            fname = fd.get("name") or fid
            attached_info.append(f"{fname} ({fid})")
        attached_info.extend(n for n in project_file_names if n not in [a.split(" (")[0] for a in attached_info])
        files_str = ", ".join(attached_info)
        response_text = f"Mock Onyx answer to: {user_actual_text} [Attached files: {files_str}]"
    else:
        response_text = f"Mock Onyx answer to: {user_actual_text}"

    if session_id and session_id in STATE["chat_sessions"]:
        STATE["chat_sessions"][session_id]["history"].append({
            "role": "assistant",
            "content": response_text,
        })

    if stream:
        def generate_sse():
            chunks = [response_text[i:i + 10] for i in range(0, len(response_text), 10)]
            if not chunks:
                chunks = [response_text]
            for chunk in chunks:
                if chunk_delay > 0:
                    time.sleep(chunk_delay)
                payload = json.dumps({"answer_piece": chunk})
                yield f"data: {payload}\n\n"
            yield "data: [DONE]\n\n"

        return Response(
            generate_sse(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    return jsonify({
        "chat_session_id": session_id,
        "answer": response_text,
        "answer_citationless": response_text,
    }), 200


def create_mock_app():
    """Factory function to create Flask app instance."""
    return app


def main():
    parser = argparse.ArgumentParser(description="Mock Onyx/Danswer API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to listen on")
    parser.add_argument("--port", type=int, default=8080, help="Port to listen on")
    args = parser.parse_args()

    print(f"Starting Mock Onyx Server on http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, threaded=True)


if __name__ == "__main__":
    main()
