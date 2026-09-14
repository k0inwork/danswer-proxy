"""Black-box conformance checks for the todo_cli scenario.

Runs the produced todo.py exactly like a user would (subprocess + TODO_DB)
and reports every spec deviation. Deterministic: no LLM in the loop.
"""
import os
import subprocess
import sys
import tempfile

TODO = "todo.py"


def _run(workspace: str, *args: str, db: str) -> tuple:
    env = dict(os.environ)
    env["TODO_DB"] = db
    p = subprocess.run(
        [sys.executable, TODO, *args],
        cwd=workspace, env=env,
        capture_output=True, text=True, timeout=30,
    )
    return p.returncode, p.stdout, p.stderr


def _add(workspace: str, text: str, db: str):
    return _run(workspace, "add", text, db=db)


def conformance_checks(workspace: str) -> list:
    """Return a list of failure strings (empty = all pass)."""
    failures = []
    if not os.path.exists(os.path.join(workspace, TODO)):
        return [f"{TODO} not found in workspace root"]

    with tempfile.TemporaryDirectory() as td:
        db = os.path.join(td, "todos.json")

        # 1) add
        rc, out, err = _add(workspace, "write report", db=db)
        if rc != 0 or out.strip() != "Added #1: write report":
            failures.append(f"add #1: rc={rc} out={out.strip()!r} err={err.strip()[:120]!r}")

        rc, out, err = _add(workspace, "buy milk", db=db)
        if rc != 0 or out.strip() != "Added #2: buy milk":
            failures.append(f"add #2: rc={rc} out={out.strip()!r}")

        # 2) list
        rc, out, err = _run(workspace, "list", db=db)
        expected = "#1 [ ] write report\n#2 [ ] buy milk"
        if rc != 0 or out.strip() != expected:
            failures.append(f"list: rc={rc} out={out.strip()!r} expected={expected!r}")

        # 3) done
        rc, out, err = _run(workspace, "done", "1", db=db)
        if rc != 0 or out.strip() != "Done #1":
            failures.append(f"done #1: rc={rc} out={out.strip()!r}")
        rc, out, err = _run(workspace, "list", db=db)
        if "#1 [x] write report" not in out:
            failures.append(f"list after done: done marker missing; out={out.strip()!r}")

        # 4) rm + smallest-free-id reuse
        rc, out, err = _run(workspace, "rm", "1", db=db)
        if rc != 0 or out.strip() != "Removed #1":
            failures.append(f"rm #1: rc={rc} out={out.strip()!r}")
        rc, out, err = _add(workspace, "new task", db=db)
        if rc != 0 or out.strip() != "Added #1: new task":
            failures.append(f"add after rm (id reuse): rc={rc} out={out.strip()!r}")

        # 5) persistence across processes (same db, fresh processes each time
        # above already prove this, but verify content explicitly)
        rc, out, err = _run(workspace, "list", db=db)
        if "#2 [ ] buy milk" not in out or "#1 [ ] new task" not in out:
            failures.append(f"persistence/list: out={out.strip()!r}")

        # 6) empty list
        with tempfile.TemporaryDirectory() as td2:
            db2 = os.path.join(td2, "todos.json")
            rc, out, err = _run(workspace, "list", db=db2)
            if rc != 0 or out.strip() != "No todos.":
                failures.append(f"empty list: rc={rc} out={out.strip()!r}")

        # 7) exit codes for unknown ids
        for cmd in ("done", "rm"):
            rc, out, err = _run(workspace, cmd, "99", db=db)
            if rc == 0:
                failures.append(f"{cmd} 99 (unknown id) must exit non-zero, got rc=0 out={out.strip()!r}")

        # 8) unknown command
        rc, out, err = _run(workspace, "frobnicate", db=db)
        if rc == 0:
            failures.append(f"unknown command must exit non-zero, got rc=0 out={out.strip()!r}")

        # 9) missing storage file must not crash
        with tempfile.TemporaryDirectory() as td3:
            db3 = os.path.join(td3, "fresh.json")
            rc, out, err = _add(workspace, "first", db=db3)
            if rc != 0 or "Traceback" in err:
                failures.append(f"add to fresh db: rc={rc} err={err.strip()[:120]!r}")

    return failures
