"""
End-to-end verification cycle for the danswer-proxy.

Cycle:
  1. Creates a fresh temp workspace with a single seed file (task_spec.txt).
  2. Starts the proxy (app.py) against the real Onyx suite (DANSWER_URL / DANSWER_API_TOKEN).
  3. Drives a client (direct OpenAI-compatible HTTP by default, or openclaude CLI)
     through a small programming task:
       a) model reads the one uploaded file
       b) answer is correct w.r.t. the file content
       c) exactly one TOP_FOLDER_* top-root file exists in the Onyx project
       d) files the model writes land on disk AND are synced by the watcher to Onyx
  4. Verifies every assertion against the real Onyx API and prints a summary.

Usage:
  python harness/run_cycle.py                      # HTTP client
  python harness/run_cycle.py --client openclaude  # openclaude CLI as client
  python harness/run_cycle.py --sync-timeout 120
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from typing import Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from harness.onyx_check import OnyxChecker  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)


CYCLE_WS = os.path.join(HERE, ".cycle_workspace")


def log(msg: str) -> None:
    print(f"[harness] {msg}", flush=True)


SEED_FILE = "sample_utils.py"
SEED_CANONICAL = "FILE_sample_utils_py.txt"
NAMING_ANSWER = "snake_case"


def make_workspace() -> str:
    """Prepare the fixed cycle workspace. The folder path is stable, so Onyx
    reuses the same `workspace-<md5>` project across runs (existing files are
    refreshed in place via the watcher's hash-based sync)."""
    os.makedirs(CYCLE_WS, exist_ok=True)
    for stale in os.listdir(CYCLE_WS):
        if stale != "workspace_sync_cache.json":
            path = os.path.join(CYCLE_WS, stale)
            shutil.rmtree(path) if os.path.isdir(path) else os.remove(path)
    seed = '''"""Utility helpers."""

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30


def get_display_name(user_id):
    user_record = fetch_user(user_id)
    display_name = user_record["name"]
    return display_name


def retry_connect(target_host, max_attempts=MAX_RETRIES):
    last_error = None
    for attempt_index in range(max_attempts):
        try:
            return connect(target_host)
        except ConnectionError as err:
            last_error = err
    raise last_error
'''
    with open(os.path.join(CYCLE_WS, SEED_FILE), "w", encoding="utf-8") as f:
        f.write(seed)
    log(f"Workspace: {CYCLE_WS} (seed={SEED_FILE})")
    return CYCLE_WS


class ProxyHandle:
    def __init__(self, workspace: str, port: int, danswer_url: str, token: str):
        self.port = port
        self.workspace = workspace
        self.danswer_url = danswer_url
        self.token = token
        self.proc: Optional[subprocess.Popen] = None
        self.mock_proc: Optional[subprocess.Popen] = None
        self.log_path = os.path.join(HERE, ".cycle_proxy.log")
        self.logf = open(self.log_path, "w", encoding="utf-8")

    def start(self) -> None:
        env = dict(os.environ)
        env["DANSWER_URL"] = self.danswer_url
        env["DANSWER_API_TOKEN"] = self.token
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(REPO, "app.py"), "-f", self.workspace, "-p", str(self.port)],
            cwd=REPO,
            env=env,
            stdout=self.logf,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{self.port}"
        for _ in range(60):
            if self.proc.poll() is not None:
                raise RuntimeError("proxy exited during startup, see proxy.log")
            try:
                r = requests.get(f"{base}/health", timeout=2)
                if r.status_code == 200:
                    log(f"Proxy up on {base} (pid {self.proc.pid})")
                    return
            except Exception:
                pass
            time.sleep(1)
        raise RuntimeError("proxy did not become healthy in time")

    def stop(self) -> None:
        for proc in [self.proc, getattr(self, "mock_proc", None)]:
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except Exception:
                    proc.kill()
        if hasattr(self, "logf"):
            self.logf.close()

    def start_mock_onyx(self, mock_port: int) -> str:
        """Start the mock Onyx server; returns the base URL to point the proxy at."""
        self.mock_proc = subprocess.Popen(
            [sys.executable, "-m", "orchestrator.mock_onyx_server", "--port", str(mock_port)],
            cwd=REPO,
            stdout=self.logf,
            stderr=subprocess.STDOUT,
        )
        base = f"http://127.0.0.1:{mock_port}"
        for _ in range(30):
            try:
                requests.get(f"{base}/api/persona", timeout=2)
                log(f"Mock Onyx up on {base}")
                return base
            except Exception:
                time.sleep(0.5)
        raise RuntimeError("mock Onyx server did not start")


def chat_completion(port: int, prompt: str, conversation_id: str, timeout: float = 300.0) -> str:
    r = requests.post(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        json={
            "model": "claude-sonnet-4.6",
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        },
        headers={"X-Conversation-ID": conversation_id},
        timeout=timeout,
    )
    r.raise_for_status()
    data = r.json()
    msg = data["choices"][0]["message"]
    # Agentic tool_call round-trips (write_file etc.): acknowledge so the
    # proxy can continue; its result arrives on the next GET of the answer.
    return msg.get("content") or ""


def run_openclaude(workspace: str, port: int, prompt: str, model: str) -> str:
    env = dict(os.environ)
    env.update({
        "OPENAI_API_BASE": f"http://127.0.0.1:{port}/v1",
        "OPENAI_API_KEY": "harness-dummy",
        "ANTHROPIC_API_KEY": "",
    })
    cmd = ["openclaude", "-p", prompt, "--model", model]
    log(f"Running: {' '.join(cmd)}")
    res = subprocess.run(
        cmd, cwd=workspace, env=env, capture_output=True, text=True, timeout=900
    )
    if res.returncode != 0:
        log(f"openclaude stderr (tail): {res.stderr[-2000:]}")
        raise RuntimeError(f"openclaude exited with {res.returncode}")
    return res.stdout


QUESTION_PROMPT = (
    "Please read the file sample_utils.py from my workspace. "
    "Question: which naming convention is used for variables in that file? "
    "Answer with just the convention name (e.g. camelCase, snake_case, PascalCase)."
)

EDIT_PROMPT = (
    "Please update my workspace file sample_utils.py: use your local write_file tool "
    "to add a short one-line docstring to the function get_display_name. Keep the rest "
    "of the file unchanged."
)


def verify(args, checker: OnyxChecker, workspace: str, answer: str) -> list[str]:
    failures = []
    project_name = "workspace-" + __import__("hashlib").md5(
        os.path.abspath(workspace).encode()
    ).hexdigest()

    # (a) read: descriptor for the seed file registered in Onyx project
    overview = {}
    for _ in range(20):
        overview = checker.project_overview(project_name)
        if overview.get("exists") and overview.get("file_file_entries"):
            break
        time.sleep(1)
    if not overview.get("exists"):
        failures.append(f"a) Onyx project '{project_name}' not found")
    elif not any(f.get("name") == SEED_CANONICAL for f in overview["file_file_entries"]):
        failures.append(f"a) {SEED_CANONICAL} not in project files: {overview['file_names']}")
    else:
        log("a) OK: sample_utils.py uploaded and registered in Onyx project")

    # (b) answer content correctness
    if args.target == "mock":
        # Mock answers by listing the attached descriptors: proves descriptor flow.
        ok_b = "FILE_sample_utils_py.txt" in answer
        log("b) " + ("OK: mock attached-descriptor flow visible in answer" if ok_b else f"FAIL: descriptor not referenced; answer: {answer[:300]!r}"))
    else:
        ok_b = NAMING_ANSWER in answer.lower()
        log("b) " + f"OK: answer correctly states the variable naming convention ({NAMING_ANSWER})" if ok_b else f"b) answer does not state '{NAMING_ANSWER}'; answer: {answer[:500]!r}")
    if not ok_b:
        failures.append("b) answer did not use the attached file content correctly")

    # (c) exactly one top_root file, no duplicate canonical names
    top = overview.get("top_root_files", [])
    if len(top) == 1:
        log(f"c) OK: exactly one top-root file: {top[0]}")
    else:
        failures.append(f"c) expected exactly 1 TOP_FOLDER_ file, found {len(top)}: {top}")
    names = overview.get("file_names", [])
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        failures.append(f"c) duplicate file entries in project: {dupes}")

    # (d) write landed on disk AND watcher synced it to Onyx.
    # Live: a real docstring (triple quotes) after the function def.
    # Mock: the deterministic marker content.
    def edit_present(text: str) -> bool:
        if not text:
            return False
        if args.target == "live":
            return '"""' in text.split("def get_display_name", 1)[-1][:300]
        return "[UPDATED_BY_MOCK_WORKSPACE]" in text

    sol_path = os.path.join(workspace, SEED_FILE)
    disk = open(sol_path, encoding="utf-8").read() if os.path.exists(sol_path) else ""
    if edit_present(disk):
        log(f"d) OK: edit written into {SEED_FILE} on disk")
    else:
        failures.append(f"d) expected write not present in {SEED_FILE} on disk")

    pid = overview.get("project_id")
    deadline = time.time() + args.sync_timeout
    synced_blob = None
    while time.time() < deadline:
        synced_blob = checker.fetch_synced_content(pid, SEED_CANONICAL)
        if synced_blob and edit_present(synced_blob):
            break
        time.sleep(2)
    if synced_blob and edit_present(synced_blob):
        rev = re.search(r"REVISION:\s*(\d+)", synced_blob)
        log(f"d) OK: watcher synced updated {SEED_CANONICAL} to Onyx (revision={rev.group(1) if rev else '?'})")
    else:
        failures.append(
            f"d) updated {SEED_CANONICAL} not synced to Onyx within {args.sync_timeout}s; blob: {None if synced_blob is None else synced_blob[:300]!r}"
        )

    return failures


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8199)
    ap.add_argument("--mock-port", type=int, default=8198)
    ap.add_argument("--target", choices=["mock", "live"], default="mock",
                    help="mock: run against the in-repo mock Onyx server; live: real DANSWER_URL suite")
    ap.add_argument("--client", choices=["http", "openclaude"], default="http")
    ap.add_argument("--model", default="claude-sonnet-4.6", help="model for openclaude")
    ap.add_argument("--sync-timeout", type=float, default=60.0, help="seconds to wait for watcher sync (d)")
    args = ap.parse_args()

    if args.target == "live":
        danswer_url = os.environ.get("DANSWER_URL")
        token = os.environ.get("DANSWER_API_TOKEN")
        if not danswer_url or not token:
            log("ERROR: DANSWER_URL and DANSWER_API_TOKEN must be set for --target live")
            return 2
    else:
        danswer_url = f"http://127.0.0.1:{args.mock_port}"
        token = "mock-token"

    checker = OnyxChecker(danswer_url, token)
    workspace = make_workspace()
    proxy = ProxyHandle(workspace, args.port, danswer_url, token)
    conversation_id = f"harness-cycle-{int(time.time())}"

    edit_prompt = EDIT_PROMPT
    if args.target == "mock":
        edit_prompt += " [TRIGGER_TOOL_WRITE_FILE:sample_utils.py]"

    answer = ""
    failures: list[str] = []
    try:
        if args.target == "mock":
            proxy.start_mock_onyx(args.mock_port)
        proxy.start()

        def run_client(prompt: str) -> str:
            if args.client == "openclaude":
                return run_openclaude(workspace, args.port, prompt, args.model)
            return chat_completion(args.port, prompt, conversation_id)

        log(f"Turn 1: reading question via client={args.client} target={args.target} ...")
        answer = run_client(QUESTION_PROMPT)
        log(f"Client answer (first 400 chars): {answer[:400]!r}")

        log("Turn 2: file edit request ...")
        edit_answer = run_client(edit_prompt)
        log(f"Edit answer (first 200 chars): {edit_answer[:200]!r}")

        failures = verify(args, checker, workspace, answer)
    except Exception as exc:
        failures.append(f"harness error: {exc}")
    finally:
        proxy.stop()
        log(f"Workspace kept at {workspace} (proxy log: {proxy.log_path})")

    print("\n===== CYCLE RESULT =====")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("ALL CHECKS PASSED (a, b, c, d)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
