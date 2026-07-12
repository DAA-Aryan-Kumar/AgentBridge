"""Server-Sent Events off the R10 bus — the frontend's realtime signal.

Frames are deliberately MINIMAL (type + chat + ids): the client refetches
through the read model, so no body — encrypted or not — ever rides the
stream. A dropped frame only delays a repaint until the fallback poll.
"""

from __future__ import annotations

import json
from typing import Iterator

from ..mesh import eventbus
from ..mesh.eventbus import Event, Subscription
from .context import GuiApp

__all__ = ["frame", "stream"]


def frame(ev: Event) -> dict:
    out = {"type": ev.type, "chat_id": ev.chat_id, "ns": ev.ns}
    if ev.type == eventbus.MESSAGE:
        out["id"] = ev.data.get("id", "")
        out["from"] = ev.data.get("from", "")
    elif ev.type == eventbus.CHAT_UPDATE:
        out["event"] = (ev.data.get("event") or {}).get("type", "")
    elif ev.type == eventbus.ADDED_TO_CHAT:
        out["by"] = ev.data.get("by", "")
    return out


def stream(app: GuiApp, sub: Subscription, ping_s: float) -> Iterator[bytes]:
    """Yield SSE frames until the session changes (logout) or the caller's
    write fails (client gone). Idle gaps carry comment pings so proxies and
    the client can tell a quiet stream from a dead one."""
    mesh = app.mesh
    yield b": connected\n\n"
    while app.mesh is mesh:
        ev = sub.get(timeout=ping_s)
        if app.mesh is not mesh:
            break
        if ev is None:
            yield b": ping\n\n"
            continue
        yield f"data: {json.dumps(frame(ev))}\n\n".encode()
