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
                    # Guard against a squatter service on the port: only OUR
                    # proxy reports this shape. Otherwise openclaude would
                    # silently talk to the wrong backend.
                    body = r.json()
                    if "orchestrator_initialized" in body and "danswer_url" in body:
                        log(f"Proxy up on {base} (pid {self.proc.pid})")
                        return
                    raise RuntimeError(
                        f"port {self.port} is occupied by another service (health: {str(body)[:200]!r}); "
                        "free it and rerun"
                    )
            except requests.RequestException:
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


class TranscriptClient:
    """ID-less client: resends the full transcript each request (like
    openclaude) so the proxy's history-matched session reuse is exercised."""

    def __init__(self, port: int):
        self.port = port
        self.messages: list[dict] = []

    def send(self, prompt: str, timeout: float = 300.0) -> str:
        self.messages.append({"role": "user", "content": prompt})
        deadline = time.time() + timeout
        while True:
            r = requests.post(
                f"http://127.0.0.1:{self.port}/v1/chat/completions",
                json={"model": "claude-sonnet-4.6", "messages": self.messages, "stream": False},
                timeout=timeout,
            )
            if r.status_code == 429:
                wait = float(r.headers.get("Retry-After", "5"))
                log(f"429 rate limited; retrying in {wait}s ...")
                if time.time() + wait > deadline:
                    raise RuntimeError("rate limit retry window exceeded")
                time.sleep(wait)
                continue
            r.raise_for_status()
            data = r.json()
            answer = data["choices"][0]["message"].get("content") or ""
            self.messages.append({"role": "assistant", "content": answer})
            return answer


def setup_openclaude_profile(port: int) -> Optional[str]:
    """Point openclaude at the harness proxy by temporarily activating a
    dedicated provider profile. Returns the previously active profile id so
    restore_openclaude_profile() can put it back. (The saved profile overrides
    OPENAI_BASE_URL env vars, so editing the config is the only reliable way.)"""
    path = os.path.expanduser("~/.openclaude.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    previous_active = cfg.get("activeProviderProfileId")
    profiles = [p for p in cfg.get("providerProfiles", []) if p.get("name") != "harness"]
    profiles.append({
        "id": "provider_harness_cycle",
        "name": "harness",
        "provider": "ollama",  # openai-compatible passthrough
        "baseUrl": f"http://127.0.0.1:{port}/v1",
        "model": "any",
    })
    cfg["providerProfiles"] = profiles
    cfg["activeProviderProfileId"] = "provider_harness_cycle"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    return previous_active


def restore_openclaude_profile(previous_active: Optional[str]) -> None:
    if previous_active is None:
        return
    path = os.path.expanduser("~/.openclaude.json")
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg["activeProviderProfileId"] = previous_active
    cfg["providerProfiles"] = [
        p for p in cfg.get("providerProfiles", []) if p.get("id") != "provider_harness_cycle"
    ]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def run_openclaude(workspace: str, port: int, prompt: str, model: str, continue_session: bool = False) -> str:
    env = dict(os.environ)
    env.update({
        "OPENAI_API_BASE": f"http://127.0.0.1:{port}/v1",
        "OPENAI_BASE_URL": f"http://127.0.0.1:{port}/v1",
        "OPENAI_API_KEY": "harness-dummy",
        "ANTHROPIC_API_KEY": "",
    })
    cmd = ["openclaude", "-p", prompt, "--model", model, "--permission-mode", "bypassPermissions",
           "--debug-file", os.path.join(workspace, "..", "openclaude-debug.log")]
    if continue_session:
        # Continue the most recent conversation in this directory: the CLI
        # resends its own transcript, exactly like real multi-turn usage.
        cmd.insert(1, "-c")
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

# Exercised only with the openclaude client: asks the client to use one of its
# OWN native tools (the Agent sub-agent). The proxy must pass those tools
# through untouched instead of stub-executing them.
SUBAGENT_PROMPT = (
    "Report the variable naming convention used in sample_utils.py by delegating "
    "the file read to a sub-agent. [TRIGGER_TOOL_CLIENT:Agent]"
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
        # Mock proves the seed file was visible via project/descriptor flow.
        ok_b = "FILE_sample_utils_py.txt" in answer or "FILE_sample_utils_py.txt" in str(answer) + overview.get("__placeholder__", "")
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
    # openclaude routes via its (temporarily swapped) provider profile to
    # 127.0.0.1:<port>/v1, so any --port works.
    port = args.port
    proxy = ProxyHandle(workspace, port, danswer_url, token)
    client = TranscriptClient(port)

    edit_prompt = EDIT_PROMPT
    if args.target == "mock":
        edit_prompt += " [TRIGGER_TOOL_WRITE_FILE:sample_utils.py]"

    answer = ""
    failures: list[str] = []
    prev_profile = setup_openclaude_profile(port) if args.client == "openclaude" else None
    try:
        if args.target == "mock":
            proxy.start_mock_onyx(args.mock_port)
        proxy.start()

        def run_client(prompt: str, continue_session: bool = False) -> str:
            if args.client == "openclaude":
                return run_openclaude(workspace, port, prompt, args.model, continue_session=continue_session)
            return client.send(prompt)

        log(f"Turn 1: reading question via client={args.client} target={args.target} ...")
        answer = run_client(QUESTION_PROMPT)
        log(f"Client answer (first 400 chars): {answer[:400]!r}")

        log("Turn 2: file edit request ...")
        edit_answer = run_client(edit_prompt, continue_session=True)
        log(f"Edit answer (first 200 chars): {edit_answer[:200]!r}")

        # History-matched session reuse: turn 2 resends turn 1's transcript,
        # so the proxy must have reused the Onyx session instead of making a
        # new one. Only meaningful for the built-in HTTP client.
        if args.client == "http":
            proxy_log = open(proxy.log_path, encoding="utf-8").read()
            if "History match: reusing conversation" in proxy_log:
                log("e) OK: history-matched session reuse active (turn 2 reused the session)")
            else:
                failures.append("e) history-matched session reuse did not trigger on turn 2")

        checks = "a, b, c, d" + (", e" if args.client == "http" else "")

        # Turn 3 (openclaude only): exercise a client-native tool (Agent
        # sub-agent). The proxy must pass it through; the sub-agent's own
        # requests also flow through the proxy. Fresh session (-c off):
        # continued sessions tend to answer "nothing pending" without ever
        # launching the sub-agent.
        if args.client == "openclaude":
            log("Turn 3: client-native Agent sub-agent request ...")
            sub_answer = run_client(SUBAGENT_PROMPT, continue_session=False)
            log(f"Sub-agent answer (first 300 chars): {sub_answer[:300]!r}")
            proxy_log = open(proxy.log_path, encoding="utf-8").read()
            passed_f = True
            if "client-native tools" not in proxy_log:
                failures.append("f) proxy log shows no client-native tool passthrough (Agent tool not seen)")
                passed_f = False
            # The sub-agent must have actually READ the file through the proxy:
            # live -> real naming convention; mock -> deterministic file marker.
            if args.target == "live":
                content_ok = NAMING_ANSWER in sub_answer.lower()
            else:
                content_ok = "FILE_sample_utils_py.txt" in sub_answer
            if not content_ok:
                failures.append(
                    f"f) sub-agent answer lacks expected file content; answer: {sub_answer[:500]!r}"
                )
                passed_f = False
            if passed_f:
                log("f) OK: client-native Agent tool passed through; sub-agent ran through the proxy")
            checks += ", f"

        failures.extend(verify(args, checker, workspace, answer))
    except Exception as exc:
        failures.append(f"harness error: {exc}")
    finally:
        proxy.stop()
        restore_openclaude_profile(prev_profile)
        log(f"Workspace kept at {workspace} (proxy log: {proxy.log_path})")

    print("\n===== CYCLE RESULT =====")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print(f"ALL CHECKS PASSED ({checks})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
