---
name: agent-bridge
description: Send/receive messages and files between Claude and CoCo (Cortex Code on the remote Snowflake machine) via the AgentBridge synced-folder message bus. Use when the user says "ask CoCo", "send to CoCo", "check CoCo's reply", "message the remote agent", or when a Snowflake-side question needs CoCo to run queries.
---

# AgentBridge — talking to CoCo

CoCo is Cortex Code (Opus-based Snowflake agent, junior-intern capability) on a remote
machine. Messages travel through a folder on the **EmployBridge SharePoint**
(`AgentBridge (AK)` in Shrishti Suyog's OneDrive, shared to aryan.kumar@employbridge.com),
synced locally via the OneDrive client. The app is
`C:\Users\AryanKumar\Downloads\AgentBridge\bridge.py` (docs in README.md there).
This machine's role is `claude`; the synced folder path is in
`%USERPROFILE%\.agentbridge\config.json` — if that config is missing, local setup is
incomplete (run `setup_claude_side.ps1` after the OneDrive shortcut has synced).

**HARD SCOPE RULE: never read, edit, or delete anything on the EB SharePoint outside the
`AgentBridge (AK)` folder — other folders contain sensitive client data.**

## Commands

```powershell
$b = "C:\Users\AryanKumar\Downloads\AgentBridge\bridge.py"
python $b status                          # channel state (seq/ack both sides)
python $b send "short text" --type task   # send; types: chat|task|result|control|ping
python $b send --body-file msg.md --attach data.csv   # long text / file transfer
python $b recv --wait 300 --mark          # poll up to N seconds for reply, then ack
python $b log --tail 20                   # conversation transcript
python $b publish                         # push new bridge.py version (peer self-updates)
```

## Rules of engagement

- **Long or quote-heavy messages: always `--body-file`** (write the message to the
  scratchpad first). Inline quoting through PowerShell breaks on embedded quotes.
- **Never edit files in the shared folder by hand** — single-writer protocol; use commands.
- Sync latency is seconds-to-a-minute each way. For a query task expect minutes:
  send, then `recv --wait 300 --mark`, and if nothing arrives report state to the user
  rather than blocking forever (`status` shows whether CoCo has even acked).
- CoCo is junior: give it exact fully-qualified table names, exact SQL when possible,
  one task per message, and ask it to attach results as files.
- Writing a task prompt for CoCo? Follow the CoCo-prompt guidance in the user's KPI
  feasibility operating prompt (prioritise Probable/No KPIs, include the EB domain
  cheat-sheet, request "key findings by source" markdown).
- To upgrade the remote app: edit bridge.py locally, bump `__version__`, `publish`.
  CoCo's `watch` daemon self-updates within its poll interval.
- The app is generic and credential-free: role names are configurable
  (`init --role X --peer Y`), auth is whatever account the OneDrive sync client holds.
- Human kill-switch: `control.json` in the shared folder (`"paused": true` halts sends).
