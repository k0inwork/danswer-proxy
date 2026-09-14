# Todo REST API — Specification

Build a REST API for a todo application as a single Python 3 file named
`todo_api.py` in the workspace root, using the Flask framework (available
in the environment) and the standard-library `sqlite3` module for storage.
No other third-party dependencies.

## Storage

- SQLite database file at the path given by the `TODO_DB` environment
  variable. If `TODO_DB` is not set, use `todos.db` in the current working
  directory.
- If the database file does not exist, it is created automatically with the
  required schema on first start (do not crash).
- Schema: table `todos` with columns `id` (integer primary key), `text`
  (non-empty string), `done` (boolean, default false).

## Server

- HTTP server on port from the `TODO_PORT` environment variable, default 5001.
- Host `127.0.0.1`.
- All request and response bodies are JSON.

## Endpoints

### `POST /todos`
- Body: `{"text": "<string>"}`.
- Creates a new todo with `done = false`.
- Responds `201` with the full object: `{"id": <int>, "text": "<string>", "done": false}`.
- Missing `text` key, empty text, or non-string text: `400` with `{"error": "invalid text"}`.
- Malformed JSON body: `400` with `{"error": "invalid json"}`.

### `GET /todos`
- Responds `200` with a JSON array of all todos, oldest first:
  `[{"id": 1, "text": "...", "done": false}, ...]`.
- Empty database: `200` with `[]`.

### `GET /todos/<id>`
- Existing id: `200` with the todo object.
- Unknown id: `404` with `{"error": "not found"}`.

### `PATCH /todos/<id>`
- Body may contain `done` (boolean) and/or `text` (non-empty string);
  only the provided fields change.
- Responds `200` with the updated todo object.
- Unknown id: `404` with `{"error": "not found"}`.
- Invalid field values (`done` not boolean, `text` empty/non-string):
  `400` with `{"error": "invalid text"}` or `{"error": "invalid done"}`.
- Malformed JSON: `400` with `{"error": "invalid json"}`.

### `DELETE /todos/<id>`
- Existing id: removes it, responds `204` with an empty body.
- Unknown id: `404` with `{"error": "not found"}`.

## ID rules

- Ids are positive integers.
- A new todo gets the smallest positive integer id not currently in use
  (ids of deleted todos are reused).

## General rules

- Unknown paths: `404` with `{"error": "not found"}`.
- Wrong method on a known path: `405` with `{"error": "method not allowed"}`.
- Every non-204 response has `Content-Type: application/json`.
- The app must never print a traceback to the client for handled errors.
- `GET /health` must respond `200` with `{"status": "ok"}` (used by tests
  to detect readiness).
