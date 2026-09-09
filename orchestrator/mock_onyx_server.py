"""
Mock Onyx / Danswer server implementation for testing and local development.
Simulates Onyx REST API endpoints and SSE streaming.
"""

import argparse
import json
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

    file_descriptor = {
        "id": file_id,
        "name": filename,
        "type": "plain_text",
        "chat_file_type": "plain_text",
    }

    STATE["uploaded_files"][file_id] = file_descriptor

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
def attach_file_to_project(project_id: str, file_id: str):
    """Link uploaded file to project."""
    if project_id not in STATE["project_files"]:
        STATE["project_files"][project_id] = []

    descriptor = STATE["uploaded_files"].get(file_id) or {
        "id": file_id,
        "name": f"file-{file_id}",
        "type": "plain_text",
    }

    if not any(f["id"] == file_id for f in STATE["project_files"][project_id]):
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


@app.route("/api/chat/send-chat-message", methods=["POST"])
def send_chat_message():
    """Send a chat message to Onyx (supports JSON & SSE streaming)."""
    data = request.get_json(silent=True) or {}
    message = data.get("message", "")
    stream = data.get("stream", False)
    session_id = data.get("chat_session_id")

    response_text = f"Mock Onyx answer to: {message}"

    if stream:
        def generate_sse():
            chunks = [response_text[i:i + 10] for i in range(0, len(response_text), 10)]
            if not chunks:
                chunks = [response_text]
            for chunk in chunks:
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
