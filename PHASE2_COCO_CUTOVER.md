# Phase 2 — CoCo cutover runbook (legacy handler → symmetric mesh worker)

Retires the legacy `bridge.py watch` → `handler_coco.py` path for CoCo and
replaces it with the one symmetric worker (`agent_worker.py coco`). **Run every
command on the Snowflake box** (Windows user `aryan.kumar`), where Cortex Code
runs. Nothing here touches this repo's `server.py`/`mesh.py`/frontend.

> **The one rule that makes this safe:** exactly ONE thing serves CoCo at a
> time. Stop the legacy watch **before** starting the mesh worker, or CoCo is
> double-served → duplicate replies (the known un-guarded duplicate-reply bug).
> The mesh worker's single-instance lock only guards against two *mesh* workers;
> it cannot see the legacy handler.

Box paths (from `legacy/REMOTE_SETUP.md`, confirmed via the live
`status/coco_run.json`):

| What | Path on the Snowflake box |
|---|---|
| OS user / home | `C:\Users\aryan.kumar` |
| Legacy install | `C:\AgentBridge\` (`bridge.py`, `handler_coco.py`, `disallowed_tools.json`) |
| Shared folder | `C:\Users\aryan.kumar\OneDrive - Employbridge\Shrishti Suyog (Contractor)'s files - AgentBridge (AK)` |
| Mesh worker (new) | `C:\AgentBridgeMesh\` (repo checkout — chosen fresh so it never collides with the legacy `C:\AgentBridge\bridge.py`) |

---

## Step 0 — Pre-flight (verify, change nothing)

```powershell
python --version            # >= 3.8  (try `py --version` if not on PATH)
cortex --help               # must succeed — the worker shells out to `cortex`
# shared folder is synced:
Test-Path "C:\Users\aryan.kumar\OneDrive - Employbridge\Shrishti Suyog (Contractor)'s files - AgentBridge (AK)\mesh"
```

All three must pass before continuing. `cortex` must be on PATH (the legacy
handler already relies on that, so it should be).

---

## Step 1 — Deploy the mesh worker code

The worker needs only three things (all stdlib, no `bridge.py`, no `gui/`):
`agent_worker.py`, `mesh.py`, and the `connectors/` package.

**Option A — git (preferred; also brings the supervisor + launcher and future updates):**

```powershell
cd C:\
git clone https://github.com/DAA-Aryan-Kumar/AgentBridge.git C:\AgentBridgeMesh
# later updates:  cd C:\AgentBridgeMesh ; git pull
```

**Option B — copy via the shared folder (if the box has no git).**
Aryan stages the files into the shared folder from his machine (ask Claude to
run this — it writes `agent_worker.py`, `mesh.py`, `connectors\*` into
`<shared>\bin\mesh_worker\`), then on the box:

```powershell
mkdir C:\AgentBridgeMesh
$src = "C:\Users\aryan.kumar\OneDrive - Employbridge\Shrishti Suyog (Contractor)'s files - AgentBridge (AK)\bin\mesh_worker"
Copy-Item "$src\agent_worker.py" C:\AgentBridgeMesh\
Copy-Item "$src\mesh.py"         C:\AgentBridgeMesh\
Copy-Item "$src\connectors"      C:\AgentBridgeMesh\connectors -Recurse
```

Confirm the code loads:

```powershell
cd C:\AgentBridgeMesh
python -c "import agent_worker, mesh, connectors; print('worker code OK', agent_worker.__version__)"
```

---

## Step 2 — Write the worker config (box paths)

`C:\Users\aryan.kumar\.agentbridge\worker_coco.json` — same shape as the
dry-run-validated local copy, but with **this machine's** `shared_dir` and
`workdir`. The 15-tool blocklist and `sql_read_only:true` are identical to the
legacy `disallowed_tools.json`.

```powershell
$cfg = @'
{
  "agent": "coco",
  "shared_dir": "C:\\Users\\aryan.kumar\\OneDrive - Employbridge\\Shrishti Suyog (Contractor)'s files - AgentBridge (AK)",
  "agent_cmd": "cortex",
  "workdir": "C:\\Users\\aryan.kumar\\.agentbridge\\worker_coco",
  "poll_seconds": 10,
  "max_replies_per_hour": 30,
  "sql_read_only": true,
  "disallowed_tools": [
    "Bash", "bash", "bash_output", "kill_shell", "python_repl",
    "web_fetch", "web_search", "cron_create", "cron_delete", "cron_list",
    "notebook_actions", "team_create", "team_delete", "send_message",
    "ask_user_question"
  ],
  "timeout": 3600
}
'@
New-Item -ItemType Directory -Force "C:\Users\aryan.kumar\.agentbridge" | Out-Null
Set-Content -Path "C:\Users\aryan.kumar\.agentbridge\worker_coco.json" -Value $cfg -Encoding utf8
```

---

## Step 3 — Dry-run on the box (still serving via legacy; posts nothing)

Proves the config + mesh + cortex-command build on THIS machine before any
cutover. Safe to run while the legacy handler is still live — `--dry-run`
never posts and never writes to the mesh.

```powershell
cd C:\AgentBridgeMesh
python agent_worker.py coco --once --dry-run
```

Expect: `agent=@coco shared=...\mesh`, one `[dry-run] ... would run: cortex -w ...
--sql-read-only ... --disallowed-tools "Bash" ...` line per chat CoCo is in, and
**no** posted messages. If cortex isn't found or the path is wrong, fix before
Step 4.

---

## Step 4 — Stop the legacy handler  ← the critical ordering step

Do this **immediately before** Step 5, so CoCo is briefly served by nothing
(safe) rather than by two things (duplicate replies).

```powershell
# stop the running watch task and stop it relaunching on logon
schtasks /end    /tn "AgentBridge Watch"
schtasks /change /tn "AgentBridge Watch" /disable

# kill any lingering `bridge.py watch` process (covers a manually-started one)
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*bridge.py*watch*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# verify nothing is left
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*bridge.py*watch*" } |
  Select-Object ProcessId, CommandLine
```

The last command must print nothing. If the watch was running in a visible
terminal, Ctrl+C that window too.

> **Do NOT** stop the legacy watch by setting `"paused": true` in
> `mesh/control.json` — the mesh worker honors that **same** flag, so it would
> pause the new worker as well. Stop the legacy watch by task/process only.

---

## Step 5 — Start the symmetric mesh worker

```powershell
cd C:\AgentBridgeMesh
python agent_worker.py coco --supervise
```

- `--supervise` respawns the worker if it crashes (capped backoff).
- The single-instance lock (`~/.agentbridge/worker_coco.lock`) guarantees only
  one worker per agent; a second launch exits `rc 3`.
- For headless autostart, run `pythonw AgentWorker.pyw` instead (it discovers
  `worker_coco.json` and supervises it), or repoint the Task Scheduler task:

```powershell
schtasks /create /f /tn "AgentBridge Worker" /sc onlogon ^
  /tr "cmd /c cd /d C:\AgentBridgeMesh && start """" pythonw AgentWorker.pyw"
```

Leave the old `AgentBridge Watch` task **disabled** (Step 4) — don't delete it
until Phase 3, so rollback stays trivial.

---

## Step 6 — Verify the cutover (throwaway scratch room only)

From Aryan's GUI — **never in Platform QA 2**:

1. Create a fresh scratch room, add `@coco`, post a question that tags `@coco`.
2. Confirm **exactly one** reply, posted as a threaded reply.
3. Open **Message info** on CoCo's reply → it should now list the **task steps**
   (`record_tasks`) — the capability the legacy handler never had. This is the
   proof the cutover took.
4. Watch the next few exchanges for any **duplicate reply** (the un-guarded
   duplicate-reply bug is most likely to surface at the handover boundary).
5. Delete the scratch room afterwards.

---

## Rollback (if anything misbehaves)

```powershell
# stop the mesh worker: Ctrl+C the --supervise window, or:
Get-CimInstance Win32_Process |
  Where-Object { $_.CommandLine -like "*agent_worker.py*coco*" } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }

# bring the legacy handler back
schtasks /change /tn "AgentBridge Watch" /enable
schtasks /run    /tn "AgentBridge Watch"
```

Because the legacy install (`C:\AgentBridge\`) is untouched, rollback is just
re-enabling its task.

---

## Behavioral differences from the legacy handler (expected, not bugs)

- **Fresh Cortex session per message.** The legacy handler kept one continuous
  session (`--resume`); the mesh worker rebuilds the full context from the mesh
  each run (last ~30 messages + pins) and does not resume. Continuity comes from
  the context file, not a live session.
- `--max-turns 60` (mesh) vs `40` (legacy). Same `--sql-read-only`, same
  15-tool blocklist, same `--auto-accept-plans`, same stream-json.
- **Task history is recorded** (`mesh.record_tasks`) — the whole reason for the
  cutover; Message info now shows CoCo's steps.
- OneDrive sync lag behaves as before; the worker holds a batch until a new
  message's attachments finish syncing (10-min grace), same as the handler.

---

## Phase 3 (later — only after CoCo is stable on the worker for a while)

Delete `legacy/handler_coco.py` and its `bridge.py` `handler_cmd`/watch-dispatch
wiring; delete the disabled `AgentBridge Watch` task; update
`legacy/REMOTE_SETUP.md` to describe the worker setup. Leave `bridge.py`'s
config/util layer and `gui/server.py`'s wizard API alone — that retirement is
the separate setup/account overhaul, not this.
