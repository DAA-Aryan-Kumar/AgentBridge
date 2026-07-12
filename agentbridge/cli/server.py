"""mesh-cli v2 — the MCP server surface (R12, D9).

One server binds ONE identity's Mesh. Tools are the capability parity list:
everything a member can do in a room — send, read, react, star, pin, create
chats (all gated by the same membership/privacy layers as the GUI, R6/D18).

DELIBERATELY ABSENT (D19): every account-management operation — status,
handle, display, privacy, blocks, deletion. Those belong to the responsible
member through the GUI only; this surface never offers them, to anyone.

Event delivery: the ``next_events`` long-poll tool drains this identity's
R10 bus subscription — transport-agnostic (works over stdio), and the
CommandHook covers push-style hooks for CLI agents.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from ..core.models import Message
from ..mesh.service import Mesh

__all__ = ["build_mcp"]


def _msg_view(m: Message) -> dict[str, Any]:
    out = {
        "id": m.id, "chat": m.chat_id, "from": m.from_, "ns": m.ns, "ts": m.ts,
        "kind": m.kind.value, "body": m.body,
    }
    if m.tags:
        out["tags"] = m.tags
    if m.reply_to:
        out["reply_to"] = m.reply_to
    if m.edited:
        out["edited"] = True
    if m.deleted:
        out["deleted"] = True
    if m.reactions:
        out["reactions"] = m.reactions
    if m.event:
        out["event"] = m.event
    return out


def build_mcp(mesh: Mesh, *, server_name: str = "agentbridge-mesh") -> FastMCP:
    server = FastMCP(server_name)
    events_sub = mesh.bus.subscribe()

    # ------------------------------------------------------------- reading
    @server.tool()
    def list_chats() -> str:
        """Every chat this identity is a member of, with unread counts."""
        out = []
        for snap in mesh.membership.chats_for():
            info = {
                "id": snap.id, "kind": snap.kind.value, "name": snap.name,
                "members": sorted(snap.members),
            }
            try:
                info["unread"] = mesh.unread(snap.id)["unread"]
            except Exception:  # noqa: BLE001 — listing survives a bad chat
                pass
            out.append(info)
        return json.dumps(out, ensure_ascii=False)

    @server.tool()
    def read_messages(chat_id: str, limit: int = 50, sync_first: bool = True) -> str:
        """The newest messages of a chat (membership-gated, overlays applied)."""
        if sync_first:
            mesh.sync.sync_once([chat_id])
        msgs = mesh.messages_for(chat_id)[-max(1, min(limit, 500)):]
        return json.dumps([_msg_view(m) for m in msgs], ensure_ascii=False)

    @server.tool()
    def chat_info(chat_id: str) -> str:
        """Snapshot: kind, name, description, members+roles, permissions."""
        snap = mesh.snapshot(chat_id)
        return json.dumps({
            "id": snap.id, "kind": snap.kind.value, "name": snap.name,
            "description": snap.description,
            "members": {n: m.role.value for n, m in snap.members.items()},
            "permissions": {k: getattr(v, "value", v)
                            for k, v in snap.permissions.__dict__.items()},
        }, ensure_ascii=False)

    @server.tool()
    def who_is(user: str) -> str:
        """A member's profile as THIS identity may see it (privacy-gated),
        including the public messaging/add-to-group gates and presence."""
        prof = mesh.visible_profile(user)
        if not prof:
            return json.dumps({"error": f"unknown user @{user}"})
        prof["presence"] = mesh.presence.visible_presence(user)
        return json.dumps(prof, ensure_ascii=False)

    @server.tool()
    def my_unread() -> str:
        """Unread summary across every chat (the catch-up starting point)."""
        out = {}
        for snap in mesh.membership.chats_for():
            try:
                info = mesh.unread(snap.id)
            except Exception:  # noqa: BLE001
                continue
            if info["unread"] or info["forced_unread"]:
                out[snap.id] = info
        return json.dumps(out, ensure_ascii=False)

    # ------------------------------------------------------------- writing
    @server.tool()
    def send_message(chat_id: str, body: str, reply_to_id: str = "") -> str:
        """Post to a chat. reply_to_id threads the reply (the safer pattern —
        the recipient is notified without a tag)."""
        reply = None
        if reply_to_id:
            parent = next(
                (m for m in mesh.messages_for(chat_id) if m.id == reply_to_id), None
            )
            if parent is not None:
                reply = {"id": parent.id, "from": parent.from_,
                         "body": parent.body[:120]}
        env = mesh.post(chat_id, body, reply_to=reply)
        mesh.outbox.flush_once()
        return json.dumps({"id": env.id, "ns": env.ns})

    @server.tool()
    def edit_message(chat_id: str, message_id: str, new_body: str) -> str:
        """Edit your own message in place (author-only)."""
        mesh.edit(chat_id, message_id, new_body)
        return json.dumps({"ok": True})

    @server.tool()
    def delete_message(chat_id: str, message_id: str) -> str:
        """Delete for everyone (sender-only; leaves a tombstone)."""
        mesh.redact(chat_id, [message_id])
        return json.dumps({"ok": True})

    @server.tool()
    def react(chat_id: str, message_id: str, emoji: str = "") -> str:
        """Set your reaction on a message; empty emoji removes it."""
        mesh.react(chat_id, message_id, emoji or None)
        return json.dumps({"ok": True})

    @server.tool()
    def pin_message(chat_id: str, message_id: str) -> str:
        mesh.pin(chat_id, message_id)
        return json.dumps({"ok": True})

    @server.tool()
    def unpin_message(chat_id: str, message_id: str) -> str:
        mesh.unpin(chat_id, message_id)
        return json.dumps({"ok": True})

    @server.tool()
    def star_messages(chat_id: str, message_ids: list[str]) -> str:
        mesh.star(chat_id, message_ids)
        return json.dumps({"ok": True})

    @server.tool()
    def mark_read(chat_id: str) -> str:
        mesh.mark_read(chat_id)
        return json.dumps({"ok": True})

    # ------------------------------------------------------------ chats
    @server.tool()
    def create_dm(user: str) -> str:
        """Open (or return) a direct chat. Gated by the recipient's public
        messaging setting; an agent's owner rides along per D18."""
        snap = mesh.create_dm(user)
        mesh.outbox.flush_once()
        return json.dumps({"chat_id": snap.id, "members": sorted(snap.members)})

    @server.tool()
    def create_group(name: str, members: list[str]) -> str:
        """Create a group (owners of any agent members are pulled in)."""
        snap = mesh.create_chat(name, members=members)
        mesh.outbox.flush_once()
        return json.dumps({"chat_id": snap.id, "members": sorted(snap.members)})

    @server.tool()
    def add_members(chat_id: str, names: list[str]) -> str:
        """Add members (agents: allowed only per the group's agent-add
        toggles, D18 — never removal, that tool doesn't exist here)."""
        snap = mesh.membership.add_members(chat_id, names)
        mesh.outbox.flush_once()
        return json.dumps({"members": sorted(snap.members)})

    @server.tool()
    def leave_chat(chat_id: str) -> str:
        snap = mesh.leave(chat_id)
        mesh.outbox.flush_once()
        return json.dumps({"left": mesh.user not in snap.members})

    # ------------------------------------------------------------- events
    @server.tool()
    def next_events(timeout_s: float = 25.0, max_events: int = 50) -> str:
        """Long-poll this identity's event stream (new messages, chat
        updates, added-to-chat). Call in a loop for near-realtime delivery."""
        mesh.sync.sync_once()
        events = []
        first = events_sub.get(timeout=min(max(timeout_s, 0.0), 120.0))
        if first is not None:
            events.append(first)
            for e in events_sub.drain():
                events.append(e)
                if len(events) >= max_events:
                    break
        return json.dumps([
            {"type": e.type, "chat": e.chat_id, "ns": e.ns, "data": e.data}
            for e in events
        ], ensure_ascii=False)

    return server
