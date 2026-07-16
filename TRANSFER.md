# Machine transfer — Windows → macOS

Bring-up checklist for moving AgentBridge development to a new (macOS) machine.
Read `HANDOFF.md` for *where the project is*; this file is *how to stand it up
somewhere new*. Written 2026-07-16 at **v0.24.187**.

## 0. Repo ownership changed

The remote is now **`https://github.com/akode2803/AgentBridge.git`** (was
`DAA-Aryan-Kumar`). Both existing Windows checkouts already point at it; a fresh
clone on macOS is correct by construction:

```bash
git clone https://github.com/akode2803/AgentBridge.git
cd AgentBridge          # main == v0.24.187 (tip 951a233)
```

Everything through **R105** is on `main`. The per-session `claude/*` worktree
branches are Windows-local scaffolding — ignore them; `main` is the source of
truth.

**Account cleanup is now COMPLETE (2026-07-16, same day):** the transfer was a
GitHub repo transfer (not a delete/recreate), so stars/issues/history carried
over and the URL redirects from the old owner. `DAA-Aryan-Kumar`'s two other
personal repos (`Data-Lineage`, `batch04`) were transferred the same way.
`DAA-Aryan-Kumar` was left as a write-collaborator by GitHub's transfer flow
(standard behavior) — that access has since been **revoked** on all three
repos, `gh` CLI on the Windows box is logged out of `DAA-Aryan-Kumar` entirely
(only `akode2803` remains), and the two places in-repo that hardcoded the old
owner were fixed: `agentbridge/gui/api_updates.py`'s `RELEASES_LATEST` (the
update-check URL) and `scripts/avd_clean_install.ps1`'s `$RepoUrl` default.
`DAA-Aryan-Kumar` is no longer referenced anywhere in this repo or its access
list.

## 1. Python environment

Stdlib-only GUI, but the mesh/harness need a few deps. Use a venv named `.venv`
(the launchers and every doc assume that path):

```bash
python3.12 -m venv .venv
./.venv/bin/python -m pip install -e ".[cloud]"   # cryptography + mcp + supabase
# optional extras: ".[memory]" (qdrant + model2vec) for vector recall
```

Run everything with `./.venv/bin/python`, **never bare `python`** (same rule as
Windows: a stray interpreter misses the deps). `python check_frontend.py` must
still print 24/24; `python -m pytest tests -q` is the suite (525 passed, 1
skipped as of R105).

## 2. Local state to recreate (NOT in git, NOT secrets-in-repo)

Everything below lives in `~/.agentbridge/` and never touches the repo. **The
two you must recreate by hand — they hold secrets, so copy them across yourself;
do not commit them, do not paste them into chat:**

- **`~/.agentbridge/config.json`** — set `"mesh_root": "supabase://mesh2"`
  (the live mesh is cloud; nothing else is required for a bare launch). Or pass
  `--root supabase://mesh2` on the first launch and it's remembered.
- **`~/.agentbridge/supabase.env`** — the cloud connection. Keys present on the
  Windows box (values redacted here): `SUPABASE_URL`,
  `SUPABASE_PUBLISHABLE_KEY`, `SUPABASE_JWKS_URL`, `SUPABASE_MEMBER_EMAIL`,
  `SUPABASE_MEMBER_PASSWORD`. Copy the file over (or re-fetch from the Supabase
  dashboard). **The secret service key is deliberately gone (RLS cutover R84) —
  do not reintroduce it.**

Do **not** copy these — they are machine-local and regenerate themselves:
`keys/` (the E2EE keystore — see §3), `gui_session.json`, `applock.json`, every
`*.lock`, `harness/`, `cache/`, `*_cache/`, `inbox/`, `worker_*`. Copying locks
or a foreign keystore causes more trouble than it saves.

## 3. First launch + sign in

```bash
./.venv/bin/python -m agentbridge.gui        # opens the app window (Edge/Chrome/default)
```

The mesh itself is entirely in Supabase — there is no data to migrate. Sign in
as your account with its **password**: on a machine with no local keystore, the
login unwraps your identity key from the account and provisions this machine
(the recovery-code path). The account password and one-time recovery code are
yours — they are not written down in the repo.

## 4. Re-home the agents onto the macOS machine

This is the one non-obvious step. Each agent (`claude`, `claudemcp`, `coco`,
`coco2`) records the machine that hosts it; they are currently pinned to the
Windows box. From the signed-in app on macOS, for each agent you want to run
here, use **adopt** (Settings → Agents → the agent → adopt/​re-home, which calls
`accounts.adopt_agent`) so its identity is re-provisioned on this machine, then
start it. Until adopted, an agent's runner refuses on macOS with
"hosted on `<windows-name>`, not this machine" (by design — `runner.verify_identity`).

Run the harness the same way as the GUI:

```bash
./.venv/bin/python -m agentbridge.harness --all     # or a single agent name
```

## 5. macOS platform notes

The code is cross-platform, with these deliberate differences already handled:

- **Launchers:** `AgentBridge.pyw` / `AgentHarness.pyw` are Windows
  double-click wrappers. On macOS just run the `python -m …` commands above (or
  wrap them in a `.command` file). `desktop.py` already opens the chromeless
  app window via Edge → Chrome → default browser on darwin.
- **Restart button** (`gui/restarter.py`): process enumeration falls back to
  `ps` off Windows, and single-instance/​spawn flags no-op — so "Restart app"
  should work, but it is **the least-exercised path on macOS**; verify it once
  before relying on it.
- **Keystore at rest:** DPAPI (`crypto/dpapi.py`) is Windows-only and no-ops
  elsewhere, so the local key bundle isn't OS-wrapped at rest on macOS. The
  identity is still E2EE and password-wrapped in the account; this only affects
  local-disk hardening. Fine for dev; note it for the packaging round.
- **App lock** (`applock.json`) is scrypt/stdlib — fully portable; it just
  won't exist until you set it up again.

## 6. Where the history lives

- `HANDOFF.md` — current state (leads with R105 → R84).
- `BACKLOG.md` — the authoritative item ledger; every V-item, ticked only after
  live verification. Open items at transfer: **V88 part 3** (timer pin-style
  formatting, no-push rendering, edit-in-place), **V90** (shared formatter +
  loading-slider), **V91** (run-feed stability), **V96/V98**, **V114** (docs
  pass), **V132** (CoCo auth fix — see `docs/COCO_AUTH.md`), plus the deferred
  **C3** connector and **RLS phase 2**. Cross-chat context fetch is sketched in
  the R103 BACKLOG entry but **awaits a privacy decision** — don't build it
  without one.
- `REWRITE_PLAN.md` + `docs/` (SCALING, SECURITY_RLS, PRIVACY_MODEL, COCO_AUTH,
  DECISIONS) — the durable design record.
- The round-by-round session memory is Claude Code's own store, keyed to the
  Windows project path; it does not follow the repo. The essentials it held
  (round history, lane split, test creds, verify tooling) are mirrored into
  `HANDOFF.md` and the docs above so a fresh session on macOS is not starting
  blind.

## 7. Live fleet note (as of this transfer)

The **Windows** live fleet is still running **v0.24.180** and was auto-locked;
rounds **.181–.187 are pushed to `main` but not yet rolled onto it**. That fleet
is the *old* machine — once macOS is the home, a fresh launch there comes up at
`.187` directly. If the Windows fleet is being retired, no roll is needed; if
it's staying, unlock it and Settings → About → Update now (the window
self-reloads, R96/V131).
