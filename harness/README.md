# Harness — proxy verification cycle

## Run the proxy from anywhere (pipx)

```bash
# one-off run straight from the repo:
pipx run git+https://github.com/k0inwork/danswer-proxy.git -f /path/to/workspace -p 8080

# or install persistently:
pipx install git+https://github.com/k0inwork/danswer-proxy.git
DANSWER_URL=... DANSWER_API_TOKEN=... danswer-proxy -f /path/to/workspace
```

Requires `DANSWER_URL` / `DANSWER_API_TOKEN` in the environment (or a local mock).

---

Reproducible end-to-end cycle, runnable against the **mock Onyx server** (default, deterministic)
or the **real Onyx suite**:

1. Prepares the fixed cycle workspace (`harness/.cycle_workspace`, reused across runs so the
   Onyx `workspace-<md5>` project is reused too) with one seed file (`sample_utils.py`).
2. Starts the proxy (`app.py -f <workspace>`) plus either the mock Onyx server or the real
   suite via ambient `DANSWER_URL` / `DANSWER_API_TOKEN`.
3. Drives a client (direct OpenAI-compatible HTTP by default, or openclaude CLI) through:
   - Turn 1: comprehension question about the attached file
   - Turn 2: a file edit (write_file through the workspace tool bridge)
4. Verifies:
   - **a)** the single uploaded file is registered in the Onyx project
   - **b)** the answer is correct w.r.t. the file content
   - **c)** exactly **one** `TOP_FOLDER_*` top-root file in the project, no duplicate entries
   - **d)** the edit lands on disk **and** the watcher syncs it to Onyx (revision bump)

## Run

```bash
python harness/run_cycle.py                          # mock Onyx (deterministic)
python harness/run_cycle.py --target live            # real Onyx suite (needs env)
python harness/run_cycle.py --client openclaude      # openclaude CLI as client
python harness/run_cycle.py --sync-timeout 120
```

Exit code 0 = all checks (a–d) passed; 1 = list of failures; 2 = missing env.

## Files

- `run_cycle.py` — the driver (workspace, mock/proxy lifecycle, client, verification)
- `onyx_check.py` — Onyx API inspection helpers (project files, blob content)
- `.cycle_workspace/` — fixed reuse workspace (gitignored)
- `.cycle_proxy.log` — proxy + mock output from the last run (gitignored)
