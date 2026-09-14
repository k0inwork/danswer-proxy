"""Black-box conformance checks for the todo_api scenario.

Starts the produced todo_api.py as a subprocess (fresh SQLite db), drives
it over real HTTP, restarts it to prove persistence, and reports every
spec deviation. Deterministic: no LLM in the loop.
"""
import os
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time

import requests

APP = "todo_api.py"
PORT = 5177  # fixed test port (overridden via TODO_PORT)
BASE = f"http://127.0.0.1:{PORT}"


def _free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


class _Server:
    def __init__(self, workspace: str, db: str):
        env = dict(os.environ)
        env["TODO_DB"] = db
        env["TODO_PORT"] = str(PORT)
        self.proc = subprocess.Popen(
            [sys.executable, APP], cwd=workspace, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )

    def wait_ready(self, timeout: float = 20.0) -> str:
        """Returns an error string on failure, empty on success."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                out, err = self.proc.communicate(timeout=5)
                return f"server exited rc={self.proc.returncode}: {err.strip()[:300]!r}"
            try:
                r = requests.get(f"{BASE}/health", timeout=2)
                if r.status_code == 200:
                    return ""
            except requests.RequestException:
                pass
            time.sleep(0.3)
        return "server did not become ready in 20s"

    def stop(self):
        if self.proc.poll() is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait(timeout=5)
        # free the port for the next instance
        deadline = time.time() + 5
        while time.time() < deadline and not _free(PORT):
            time.sleep(0.2)


def _start(workspace: str, db: str) -> tuple:
    srv = _Server(workspace, db)
    err = srv.wait_ready()
    return srv, err


def _db_ids(db: str) -> list:
    try:
        con = sqlite3.connect(db)
        rows = con.execute("SELECT id FROM todos ORDER BY id").fetchall()
        con.close()
        return [r[0] for r in rows]
    except Exception:
        return []


def conformance_checks(workspace: str) -> list:
    failures = []
    if not os.path.exists(os.path.join(workspace, APP)):
        return [f"{APP} not found in workspace root"]

    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "todos.db")
        srv, err = _start(workspace, db)
        if err:
            return [f"startup: {err}"]

        try:
            # 1) POST
            r = requests.post(f"{BASE}/todos", json={"text": "write report"}, timeout=10)
            if r.status_code != 201 or r.json() != {"id": 1, "text": "write report", "done": False}:
                failures.append(f"POST #1: status={r.status_code} body={r.text[:150]!r}")

            r = requests.post(f"{BASE}/todos", json={"text": "buy milk"}, timeout=10)
            if r.status_code != 201 or r.json() != {"id": 2, "text": "buy milk", "done": False}:
                failures.append(f"POST #2: status={r.status_code} body={r.text[:150]!r}")

            # 2) GET list (oldest first)
            r = requests.get(f"{BASE}/todos", timeout=10)
            expected = [{"id": 1, "text": "write report", "done": False},
                        {"id": 2, "text": "buy milk", "done": False}]
            if r.status_code != 200 or r.json() != expected:
                failures.append(f"GET list: status={r.status_code} body={r.text[:200]!r}")

            # 3) GET one / 404
            r = requests.get(f"{BASE}/todos/1", timeout=10)
            if r.status_code != 200 or r.json().get("text") != "write report":
                failures.append(f"GET /todos/1: status={r.status_code} body={r.text[:150]!r}")
            r = requests.get(f"{BASE}/todos/99", timeout=10)
            if r.status_code != 404 or r.json() != {"error": "not found"}:
                failures.append(f"GET /todos/99: status={r.status_code} body={r.text[:150]!r}")

            # 4) PATCH done
            r = requests.patch(f"{BASE}/todos/1", json={"done": True}, timeout=10)
            if r.status_code != 200 or r.json() != {"id": 1, "text": "write report", "done": True}:
                failures.append(f"PATCH done: status={r.status_code} body={r.text[:150]!r}")

            # 5) PATCH text only
            r = requests.patch(f"{BASE}/todos/1", json={"text": "write report v2"}, timeout=10)
            if r.status_code != 200 or r.json() != {"id": 1, "text": "write report v2", "done": True}:
                failures.append(f"PATCH text: status={r.status_code} body={r.text[:150]!r}")

            # 6) PATCH 404 + invalid values
            r = requests.patch(f"{BASE}/todos/99", json={"done": True}, timeout=10)
            if r.status_code != 404:
                failures.append(f"PATCH 99: status={r.status_code} body={r.text[:150]!r}")
            r = requests.patch(f"{BASE}/todos/2", json={"done": "yes"}, timeout=10)
            if r.status_code != 400 or r.json() != {"error": "invalid done"}:
                failures.append(f"PATCH invalid done: status={r.status_code} body={r.text[:150]!r}")
            r = requests.patch(f"{BASE}/todos/2", json={"text": ""}, timeout=10)
            if r.status_code != 400 or r.json() != {"error": "invalid text"}:
                failures.append(f"PATCH invalid text: status={r.status_code} body={r.text[:150]!r}")

            # 7) POST validation
            r = requests.post(f"{BASE}/todos", data="{bad json", headers={"Content-Type": "application/json"}, timeout=10)
            if r.status_code != 400 or r.json() != {"error": "invalid json"}:
                failures.append(f"POST invalid json: status={r.status_code} body={r.text[:150]!r}")
            r = requests.post(f"{BASE}/todos", json={"text": ""}, timeout=10)
            if r.status_code != 400 or r.json() != {"error": "invalid text"}:
                failures.append(f"POST empty text: status={r.status_code} body={r.text[:150]!r}")

            # 8) DELETE + id reuse
            r = requests.delete(f"{BASE}/todos/1", timeout=10)
            if r.status_code != 204:
                failures.append(f"DELETE #1: status={r.status_code} body={r.text[:150]!r}")
            r = requests.delete(f"{BASE}/todos/99", timeout=10)
            if r.status_code != 404:
                failures.append(f"DELETE 99: status={r.status_code} body={r.text[:150]!r}")
            r = requests.post(f"{BASE}/todos", json={"text": "new task"}, timeout=10)
            if r.status_code != 201 or r.json().get("id") != 1:
                failures.append(f"POST after DELETE (id reuse): status={r.status_code} body={r.text[:150]!r}")

            # 9) wrong method / unknown path
            r = requests.delete(f"{BASE}/todos", timeout=10)
            if r.status_code != 405:
                failures.append(f"DELETE /todos (wrong method): status={r.status_code} body={r.text[:150]!r}")
            r = requests.get(f"{BASE}/nope", timeout=10)
            if r.status_code != 404:
                failures.append(f"GET /nope: status={r.status_code} body={r.text[:150]!r}")
        finally:
            srv.stop()

        # 10) persistence across restart (real SQLite on disk)
        ids_before = _db_ids(db)
        srv, err = _start(workspace, db)
        if err:
            failures.append(f"restart: {err}")
            return failures
        try:
            r = requests.get(f"{BASE}/todos", timeout=10)
            if r.status_code != 200 or len(r.json()) != 2:
                failures.append(f"persistence after restart: status={r.status_code} body={r.text[:200]!r}")
        finally:
            srv.stop()
        ids_after = _db_ids(db)
        if not ids_after or set(ids_before) != set(ids_after):
            failures.append(f"sqlite rows changed across restart: before={ids_before} after={ids_after}")

    return failures
