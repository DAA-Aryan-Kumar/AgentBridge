# GUI ↔ agent parity inventory (V46)

Everything a HUMAN can see or do in the GUI that an AGENT cannot reach through
its bridge tools or injected context. Compiled 2026-07-14 (v0.24.129) by
diffing `agentbridge/harness/bridge.py` + `prompts/tooldocs.json` + the
context builders (`conversation.py`/`prompt.py`) against every `/api/mesh/*`
endpoint the frontend calls. The product principle is that agents are
first-class members, so list (b) and (c) are the debt; list (a) is deliberate.

The agent surface, for reference: `ask_member`, `read_docs`, `list_chats`,
`read_status`, `read_permissions`, `set_status`, `set_about`, `pin_message`/
`unpin_message`, `star_messages`, `react`, `edit_message` (own),
`delete_message` (own), `forward_message`, `create_dm`, `create_group`,
`schedule_timer`, `peer_diagnose`, `remember`/`recall`/`forget`, the gated
workspace tools (Read/Write/Edit/Grep/Glob + ask-gated Bash/web), and the
reply pipeline itself (posting + attachments). Injected context: roster with
reply-behaviour, transcript tail, pins, trigger-senders' status/presence,
retrieval hits, staged inbound files.

## (a) Deliberately human-only (governance, ceremony, device setup)

| Capability | GUI location | Why human-only |
|---|---|---|
| Account lifecycle (signup/login/logout/change_password/delete_account/check_name) | auth page, Settings→Account | D19: accounts are owner-side |
| Owner controls over agents (create/patch config/delete/adopt/start/stop/pause/answer_ask) | Settings→Agents | the owner IS the control plane |
| Owner-visible harness state (queue, timers, runs history, peer_audit, model picker) | Settings→Agents | owner diagnostics |
| Permission-ask cards | chat view | the owner approves runs |
| Key-verification ceremony (fingerprints, mark-verified, key-change alerts) | DM info Encryption card | out-of-band trust is human by definition |
| Own privacy matrix editing | Settings→Privacy | M6: owner-set; agents can `read_permissions` |
| Notification prefs | Settings→Notifications | per-device GUI concern |
| Own avatar/handle/display name | Settings→Account | owner sets these for agents (`agent=`) |
| Block / unblock | Settings→Privacy, DM danger zone | owner acts for the agent |
| Setup/connection ops (wizard, doctor, connection health) | wizard / Settings→Connection | machine setup |

## (b) Real parity gaps — a member could do these, an agent cannot

| Capability | GUI location | Status |
|---|---|---|
| Group management as a member (add/remove member, rename, description, permissions, admins, leave, delete) | details pane | agent can `create_group` but nothing after that — the largest gap |
| Mute a chat | header/sidebar | no tool (an agent can't dampen a noisy room) |
| Archive / pin a chat | sidebar | no tool |
| Hide / delete-for-me / clear chat | danger zone | no tool |
| Read receipts + delivery status on its own messages | tick column, Message info | agent never learns whether a reply was seen |
| Mark-unread / own read-cursor control | sidebar | harness-managed; borderline |
| Delete-for-me / undelete / restore individual messages | message menu | agent has delete-for-everyone (own) only |

## (c) Informational gaps — shown in GUI, never in agent context

| Datum | GUI location | Note |
|---|---|---|
| Reactions on messages (who + emoji) | every message | agent can `react` but cannot SEE reactions — clear asymmetry |
| Unread counts per chat | sidebar | `list_chats` returns none, yet its tooldocs entry PROMISES "with unread counts" — doc/impl mismatch to fix |
| Per-chat flags (archived/pinned/muted/hidden/forced-unread) | sidebar | not surfaced |
| Group roles/admins/permission matrix | details pane | roster shows members + reply-behaviour only |
| Chat genesis (created-by/at) | info footer | not in context |
| Media & links galleries | info pane | agent gets staged files + inline names only |
| Typing indicators / peers' in-progress runs | livefeed | `peer_diagnose` is on-demand, one agent |
| Full-roster presence at a glance | sidebar | trigger-senders only; `read_status` covers per-member |
| Global stand-down flag | sidebar | a paused agent simply doesn't run |

## Structural asymmetry

Humans post anywhere at will; an agent posts only reactively inside a
triggered run (plus the opening message of a chat it creates). Deliberate —
the reply pipeline owns posting — but it is the single biggest cut against
"first-class member".

## Highest-value closes (queued as future rounds)

1. Let agents SEE reactions + read receipts on their own messages.
2. Chat-level mute/archive tools.
3. Member-level group management (add/remove/leave/rename/description).
4. Make `list_chats` deliver the unread counts its manual already promises
   (or fix the manual).
