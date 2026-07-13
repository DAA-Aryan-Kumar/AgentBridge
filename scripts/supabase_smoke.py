"""Live smoke for the Supabase transport (R23) — run BY HAND, never CI:

    uv run python scripts/supabase_smoke.py

Needs ~/.agentbridge/supabase.env and the one-time schema paste
(docs/supabase_schema.sql). Exercises the raw transport contract against the
real project, then a full E2EE mesh roundtrip (two identities, a chat, a
sealed message, sync) on a throwaway root, and cleans up after itself.
"""

from __future__ import annotations

import sys
import time

from agentbridge.core.timekit import new_id
from agentbridge.mesh.service import Mesh
from agentbridge.transport.supabase import SupabaseTransport, load_supabase_env


def main() -> int:
    env = load_supabase_env()
    if not env.get("SUPABASE_URL"):
        print("no credentials — put them in ~/.agentbridge/supabase.env")
        return 2
    root = f"smoke-{new_id('r')[-8:]}"
    tx = SupabaseTransport(root, env=env)
    print(f"[smoke] project {env['SUPABASE_URL']} root {root!r}")

    # ---- schema present?
    try:
        tx.list_chat_ids()
    except Exception as e:  # noqa: BLE001
        print("[smoke] SCHEMA MISSING — paste docs/supabase_schema.sql in the"
              " dashboard SQL editor first.", str(e)[:200])
        return 3

    # ---- raw transport contract
    tx.put_doc("users/probe.json", {"name": "probe"})
    assert tx.get_doc("users/probe.json")["name"] == "probe"
    assert "users/probe.json" in tx.list_docs("users/")
    tx.append_log("c1", "probe@box.jsonl", {"id": "m1", "n": 1})
    tx.append_log("c1", "probe@box.jsonl", {"id": "m2", "n": 2})
    recs, off = tx.read_log("c1", "probe@box.jsonl", 0)
    assert [r["id"] for r in recs] == ["m1", "m2"]
    recs2, _ = tx.read_log("c1", "probe@box.jsonl", off)
    assert recs2 == []
    heads = dict(tx.list_logs("c1"))
    assert heads["probe@box.jsonl"] == off
    tx.put_blob("chats/c1/files/f1.bin", b"hello-bytes")
    assert tx.get_blob("chats/c1/files/f1.bin") == b"hello-bytes"
    print("[smoke] raw transport contract OK (docs, logs, blobs)")

    # ---- realtime hint: a second transport's watcher wakes on our write
    tx2 = SupabaseTransport(root, env=env)
    w = tx2.watch()
    time.sleep(2.5)                    # let the channel subscribe
    tx.append_log("c1", "probe@box.jsonl", {"id": "m3", "n": 3})
    hinted = w.wait(10)
    print(f"[smoke] realtime hint: {'OK' if hinted else 'no (poll-only mode)'}")

    # ---- a real E2EE mesh on this transport
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        home = Path(td)
        a = Mesh(SupabaseTransport(root, env=env), "smokea", "box1",
                 encrypt=True, home=home)
        a.accounts.create_human("smokea", "smoke-pass-1")
        b = Mesh(SupabaseTransport(root, env=env), "smokeb", "box1",
                 encrypt=True, home=home)
        b.accounts.create_human("smokeb", "smoke-pass-2")
        chat = a.create_chat("Cloud Room", members=["smokeb"])
        a.post(chat.id, "hello through the cloud")
        a.outbox.flush_once()
        b.sync.sync_once([chat.id])
        bodies = [m.body for m in b.messages_for(chat.id)
                  if m.kind.value == "message"]
        assert bodies == ["hello through the cloud"], bodies
        raw = SupabaseTransport(root, env=env).read_log(
            chat.id, [n for n, _ in a.tx.list_logs(chat.id)][0], 0)[0]
        sealed = not any("hello through the cloud" in str(r) for r in raw)
        print(f"[smoke] mesh roundtrip OK — E2EE at rest: "
              f"{'SEALED' if sealed else 'PLAINTEXT (!!)'} ")
        a.close()
        b.close()

    # ---- cleanup: the throwaway root vanishes
    tx.delete_chat("c1")
    tx.delete_chat(chat.id)
    for p in tx.list_docs(""):
        tx.delete_doc(p)
    tx.close()
    tx2.close()
    print("[smoke] cleaned up — done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
