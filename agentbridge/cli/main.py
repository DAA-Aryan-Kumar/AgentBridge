"""agentbridge CLI (R12) — one install, two entry points (account-model v2):

  python -m agentbridge.cli mcp   --root PATH --user NAME [--machine M] [--encrypt]
      run the MCP server on stdio for this identity (agents' default mode;
      no password — agents never authenticate, their identity is the machine)

  python -m agentbridge.cli send  --root ... --user ... --password ... CHAT BODY
  python -m agentbridge.cli read  --root ... --user ... --password ... CHAT
  python -m agentbridge.cli chats --root ... --user ... --password ...
      human-mode conveniences: a HUMAN identity must pass the password check
      (CLI auth is humans-only; account CREATION stays GUI-only)

Account-management options (status, handle, privacy, ...) are deliberately
not here — GUI-only, per D19.
"""

from __future__ import annotations

import argparse
import platform
import sys

from ..core.errors import PermissionDenied
from ..core.models import UserKind
from ..mesh.service import Mesh


def _mesh(args) -> Mesh:
    return Mesh(
        args.root, args.user, args.machine or platform.node() or "cli",
        encrypt=args.encrypt,
    )


def _require_human_login(mesh: Mesh, password: str | None) -> None:
    kind = mesh.directory.kind(mesh.user)
    if kind is not UserKind.HUMAN:
        raise PermissionDenied("human commands need a member account (agents use mcp mode)")
    if not password or not mesh.accounts.verify_password(mesh.user, password):
        raise PermissionDenied("sign-in failed: check the username and password")
    if mesh.keystore.load(mesh.user) is None:  # unlock keys on this device
        mesh.accounts.unlock(password)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="agentbridge")
    ap.add_argument("--root", required=True, help="path to the mesh2 root")
    ap.add_argument("--user", required=True)
    ap.add_argument("--machine", default="")
    ap.add_argument("--encrypt", action="store_true", help="use E2EE sealing")
    ap.add_argument("--password", default=None, help="human commands only")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("mcp", help="run the MCP server on stdio")
    p_send = sub.add_parser("send")
    p_send.add_argument("chat_id")
    p_send.add_argument("body")
    p_read = sub.add_parser("read")
    p_read.add_argument("chat_id")
    p_read.add_argument("--limit", type=int, default=20)
    sub.add_parser("chats")

    args = ap.parse_args(argv)
    mesh = _mesh(args)
    try:
        if args.cmd == "mcp":
            from .server import build_mcp

            mesh.start(heartbeat=True)
            build_mcp(mesh).run()  # stdio transport; blocks until the client leaves
            return 0

        _require_human_login(mesh, args.password)
        if args.cmd == "chats":
            for snap in mesh.membership.chats_for():
                print(f"{snap.id}\t{snap.kind.value}\t{snap.name}")
        elif args.cmd == "send":
            env = mesh.post(args.chat_id, args.body)
            mesh.outbox.flush_once()
            print(env.id)
        elif args.cmd == "read":
            mesh.sync.sync_once([args.chat_id])
            for m in mesh.messages_for(args.chat_id)[-args.limit:]:
                who = f"@{m.from_}"
                print(f"[{m.ts}] {who}: {m.body}" if not m.event
                      else f"[{m.ts}] * {m.event.get('type')}")
        return 0
    except PermissionDenied as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    finally:
        mesh.close()


if __name__ == "__main__":
    raise SystemExit(main())
