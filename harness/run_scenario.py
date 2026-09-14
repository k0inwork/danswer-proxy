"""
Scenario-based end-to-end verification for the danswer-proxy.

Instead of the small read/write cycle (run_cycle.py), this drives a real
build task: seed a spec into the workspace, have the client (openclaude via
the proxy, or the raw HTTP transcript client) implement it, then verify the
result black-box — the harness runs the produced app itself and, on failure,
feeds the failures back to the agent for repair (CI feedback loop).

Phases:
  1. Seed        - write scenarios/<name>/spec.md into the workspace
  2. Build       - agent implements the spec (write_file calls flow through
                   the proxy's workspace sync)
  3. Conformance - harness runs checks.py against the produced app
  4. Repair loop - up to --max-attempts times: send failures back to the
                   agent, re-check
  5. Sync check  - produced files must be registered in the Onyx project

Usage:
  python harness/run_scenario.py --client openclaude                 # live
  python harness/run_scenario.py --target mock --skip-conformance    # mechanics only
"""
import argparse
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, REPO)

from harness.onyx_check import OnyxChecker  # noqa: E402
from run_cycle import (  # noqa: E402
    ProxyHandle,
    TranscriptClient,
    log,
    make_scenario_workspace,
    run_openclaude,
    restore_openclaude_profile,
    setup_openclaude_profile,
    verify_project_sync,
)

SCENARIO_DIR = os.path.join(HERE, "scenarios")

BUILD_PROMPT = (
    "Implement the application described in SPEC.md in this workspace. "
    "Read SPEC.md first, then create the file(s) exactly as specified. "
    "The spec is the contract: follow its output formats and exit codes precisely."
)

REPAIR_PROMPT = (
    "An automated conformance test run against your implementation failed. "
    "Fix {filename} so that all checks pass. Do not modify the SPEC.md.\n\n"
    "Failed checks:\n{failures}"
)


def run_conformance(scenario: str, workspace: str):
    checks_path = os.path.join(SCENARIO_DIR, scenario, "checks.py")
    namespace = {"__name__": "scenario_checks"}
    exec(compile(open(checks_path, encoding="utf-8").read(), checks_path, "exec"), namespace)
    return namespace["conformance_checks"](workspace)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scenario", default="todo_cli")
    ap.add_argument("--client", choices=["http", "openclaude"], default="openclaude")
    ap.add_argument("--target", choices=["mock", "live"], default="live")
    ap.add_argument("--model", default="claude-sonnet-4.6")
    ap.add_argument("--port", type=int, default=8199)
    ap.add_argument("--mock-port", type=int, default=8198)
    ap.add_argument("--sync-timeout", type=int, default=120)
    ap.add_argument("--max-attempts", type=int, default=3,
                    help="build + repair rounds before giving up")
    ap.add_argument("--skip-conformance", action="store_true",
                    help="only verify proxy mechanics (file sync), not app behavior")
    args = ap.parse_args()

    scenario_dir = os.path.join(SCENARIO_DIR, args.scenario)
    spec_path = os.path.join(scenario_dir, "spec.md")
    if not os.path.exists(spec_path):
        log(f"ERROR: unknown scenario '{args.scenario}' (missing {spec_path})")
        return 2

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
    workspace = make_scenario_workspace(args.scenario, spec_path)
    port = args.port
    proxy = ProxyHandle(workspace, port, danswer_url, token)
    client = TranscriptClient(port)

    def run_client(prompt: str, continue_session: bool = False) -> str:
        if args.client == "openclaude":
            return run_openclaude(workspace, port, prompt, args.model,
                                  continue_session=continue_session)
        return client.send(prompt)  # TranscriptClient keeps its own history

    answer = ""
    failures: list = []
    prev_profile = setup_openclaude_profile(port) if args.client == "openclaude" else None
    try:
        if args.target == "mock":
            proxy.start_mock_onyx(args.mock_port)
        proxy.start()

        # Phase 1+2: build
        log(f"Phase BUILD ({args.client}/{args.target}): implementing {args.scenario} ...")
        answer = run_client(BUILD_PROMPT)
        log(f"Build answer (first 300 chars): {answer[:300]!r}")

        # Phase 3+4: conformance + repair loop
        if not args.skip_conformance:
            for attempt in range(1, args.max_attempts + 1):
                failures = run_conformance(args.scenario, workspace)
                if not failures:
                    log(f"CONFORMANCE: all checks passed (attempt {attempt})")
                    break
                log(f"CONFORMANCE: {len(failures)} check(s) failed (attempt {attempt}):")
                for f in failures:
                    log(f"  - {f}")
                if attempt == args.max_attempts:
                    break
                feedback = REPAIR_PROMPT.format(filename="the implementation",
                                                failures="\n".join(f"- {x}" for x in failures))
                log(f"Phase REPAIR ({attempt}): sending failures back to the agent ...")
                answer = run_client(feedback, continue_session=True)
                log(f"Repair answer (first 200 chars): {answer[:200]!r}")
        else:
            log("CONFORMANCE: skipped (--skip-conformance)")

        # Phase 5: sync check — files the proxy uploaded must be in the project
        failures.extend(
            verify_project_sync(checker, workspace, args.sync_timeout,
                                proxy_log_path=proxy.log_path)
        )
    except Exception as exc:
        failures.append(f"harness error: {exc}")
    finally:
        proxy.stop()
        restore_openclaude_profile(prev_profile)
        log(f"Workspace kept at {workspace} (proxy log: {proxy.log_path})")

    print("\n===== SCENARIO RESULT =====")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print(f"SCENARIO '{args.scenario}' PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
