# AgentBridge

Two-way message bus between **Claude Code** (local machine) and **CoCo / Cortex Code**
(remote Snowflake machine), carried over a **OneDrive/SharePoint synced folder**.
One stdlib-only Python file (`bridge.py`) runs on both machines; a local config sets the role.

```
Claude Code ──bridge.py──> [local synced folder] ──OneDrive sync──> SharePoint cloud
                                                        │
CoCo (Cortex) <──bridge.py── [remote synced folder] <───┘
```

## Hosting & scope (EB deployment)

- The shared folder lives on the **EmployBridge tenant** (EB data stays on EB SharePoint):
  `empb-my.sharepoint.com` → Shrishti Suyog's OneDrive → `WIP/CommOps Projects/AgentBridge (AK)`.
- Access is via each user's **own EB account** (e.g. aryan.kumar@employbridge.com) — the
  OneDrive sync client holds the sign-in; **the app itself stores no credentials, tokens,
  tenant names, or user-specific paths**. Everything machine-specific lives in that
  machine's local `%USERPROFILE%\.agentbridge\config.json`, so any team member can reuse
  the app by pointing `init` at their own synced folder.
- **Hard scope rule for agents and humans alike: never read, edit, or delete anything on
  the SharePoint outside the `AgentBridge (AK)` folder.** The app enforces this
  structurally — every path it touches is derived from the configured shared folder — and
  the same rule is written into CoCo's operating prompt and Claude's skill.

## Why a synced folder (the transport decision)

| Option | Auth burden | Code burden | Corp-friendly | Audit story |
|---|---|---|---|---|
| **OneDrive/SharePoint synced folder** (chosen) | none — sync client already signed in | none — plain file I/O | best (M365 is sanctioned) | any authorized human opens the folder in SharePoint web |
| Microsoft Graph API direct | Azure AD app registration or device-code flow; tokens on disk | HTTP + refresh logic | app registrations often blocked by tenant policy | same visibility, more moving parts |
| GitHub private repo | PAT on both machines | git or REST calls | github.com may be blocked from client VDIs; PAT = secret sprawl | excellent (commit history) |
| GitHub Gists | PAT | REST | same as above; no folders, size limits | weak |

The synced folder wins because **both machines already have authenticated, policy-approved
access to the EB SharePoint**, the sync client does every upload/download for us, and there
are **zero secrets stored anywhere**. Known risk: EB conditional-access policy could block
OneDrive *client* sync on a non-EB device even though browser access works — if that
happens on the local machine, the fallbacks are (in order) a GitHub private repo, or
Graph device-code flow.

## Design principles

1. **Single writer per shared file.** Claude only writes `channel/claude.json` +
   `logs/claude.log.jsonl`; CoCo only writes `channel/coco.json` + `logs/coco.log.jsonl`.
   Sync conflicts become structurally impossible — OneDrive never sees two editors of one file.
2. **Edit in place, don't multiply files.** Each side's envelope file is overwritten per
   message (with seq/ack counters, TCP-style), so steady-state traffic touches exactly
   2 small files. History is preserved separately in append-only logs.
3. **Piggyback acknowledgements.** `ack` in my envelope = highest peer `seq` I processed.
   New mail exists when `peer.seq > my.ack`; my message is delivered when `peer.ack >= my.seq`.
4. **Everything auditable.** Every message in/out is appended to the shared `logs/*.jsonl`.
   Any human authenticated to the EB SharePoint can read the full transcript in the
   browser, and can pause both agents by setting `"paused": true` in `control.json`
   (kill-switch checked before every send and every watch cycle).
5. **Corruption-tolerant.** Atomic writes (temp + rename), SHA-256 checksums on bodies and
   attachments, BOM-tolerant JSON reads, "still syncing — retry" handling for partial files.
6. **Self-updating.** `publish` puts the running script + manifest into shared `bin/`;
   any peer running `watch` verifies the SHA-256 and hot-swaps itself, then restarts.
   Upgrades to the remote app ship without touching the remote machine.
7. **Generic by design.** Role names default to `claude`/`coco` but any pair works
   (`init --role analyst --peer sqlbot`), so other team members can run their own
   bridge instance in their own folder with their own agents.

## Shared folder layout

```
AgentBridge (AK)/                 (EB SharePoint, synced via OneDrive shortcut)
  channel/claude.json             current envelope, written only by Claude side
  channel/coco.json               current envelope, written only by CoCo side
  files/                          attachment payloads (general file transfer)
  logs/claude.log.jsonl           append-only audit log (Claude side)
  logs/coco.log.jsonl             append-only audit log (CoCo side)
  bin/version.json + bridge_*.py  self-update channel
  control.json                    human kill-switch {"paused": bool}
```

## Command reference

```
python bridge.py init --role claude|coco --shared <synced folder>   one-time setup
                      [--role X --peer Y]      custom agent pair names
python bridge.py doctor                        environment self-check
python bridge.py send "text" [--attach f]...   send message (+files); --body-file for long text
python bridge.py recv [--wait N] [--mark]      read new message; --mark acknowledges it
python bridge.py watch [--once]                daemon: poll, display, handle, ack, self-update
python bridge.py status                        seq/ack state of both sides
python bridge.py log [--tail N]                conversation transcript from audit logs
python bridge.py gui                           tkinter GUI (transcript, send box, attach)
python bridge.py publish                       push this script version to shared bin/
python bridge.py selfupdate                    pull newer version from shared bin/ if any
```

Local state lives in `%USERPROFILE%\.agentbridge` (config + inbox copies); override with
`--home` or `AGENTBRIDGE_HOME` (used for same-machine testing of both roles).

Optional config key `handler_cmd` runs a command on every inbound message in `watch` mode
(placeholders `{body_file}`, `{seq}`, `{from}`) — this is the hook for driving Cortex Code
headlessly once we learn what invocation it supports. Handler failures retry up to 3 times,
then ack-with-note so the channel never wedges.

## Current deployment status

- **App: v0.2.0 ready** (role/peer configurable, tested).
- **Claude side: waiting on one manual step** — sign the OneDrive client into the EB
  account and "Add shortcut to My files" on the shared folder, then run
  `setup_claude_side.ps1` (it finds the synced folder, runs init + doctor + publish,
  and sends the bootstrap hello to CoCo).
- **CoCo side: pending** — follow `REMOTE_SETUP.md` on the remote machine *after* the
  Claude side has published (the remote installs the app from shared `bin/`).
- The earlier scaffolding on the Accordion tenant was decommissioned 2026-07-03; EB work
  products must not transit Accordion SharePoint.

## Compiled apps?

v1 is deliberately a single Python script rather than a compiled exe: unsigned exes trip
corporate AV, and self-update for an exe is far more fragile than a file copy. If the remote
machine has no Python, the fallbacks (in order) are: Windows Store `python`, a PyInstaller
one-file exe built here and shipped via `files/`, or a PowerShell port of the protocol.
