"""The heavy soak (R24) — run BY HAND on a dev box, never CI:

    uv run python scripts/soak.py [--agents 10] [--chats 10] [--msgs 200]
    uv run python scripts/soak.py --supabase       # light cloud soak

Prints a perf table: post+flush throughput, storm convergence, offline
catch-up, read-model latency at depth, harness scan breadth, cache rebuild.
Everything runs E2EE on throwaway roots and cleans up after itself.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tests"))
from conftest import install_key, seed_account  # noqa: E402

from agentbridge.harness import AgentRunner, Reply  # noqa: E402
from agentbridge.mesh.service import Mesh  # noqa: E402
from agentbridge.transport.folder import FolderTransport  # noqa: E402

ROWS: list[tuple[str, str]] = []


def row(name: str, value: str) -> None:
    ROWS.append((name, value))
    print(f"  {name:<44} {value}")


def bench_folder(agents: int, chats: int, msgs: int) -> None:
    td = Path(tempfile.mkdtemp(prefix="ab-soak-"))
    try:
        root = td / "mesh2"
        tx = FolderTransport(root)
        bundles = {"aryan": seed_account(tx, "aryan")}
        home = td / "home"
        install_key(home, "aryan", bundles["aryan"])
        owner = Mesh(FolderTransport(root), "aryan", "soak", home=home,
                     encrypt=True)

        # ---- post throughput (one chat, sealed)
        c0 = owner.create_chat("Perf")
        t0 = time.perf_counter()
        for i in range(msgs):
            owner.post(c0.id, f"perf message {i} with a plausible length body")
        posted = time.perf_counter() - t0
        t0 = time.perf_counter()
        owner.outbox.flush_once()
        flushed = time.perf_counter() - t0
        row(f"post {msgs} sealed msgs (enqueue)", f"{msgs / posted:8.0f} msg/s")
        row(f"outbox flush {msgs} msgs to disk", f"{msgs / flushed:8.0f} msg/s")

        # ---- read-model latency at depth
        owner.sync.sync_once([c0.id])
        t0 = time.perf_counter()
        for _ in range(20):
            owner.messages_for(c0.id)
        row(f"messages_for at {msgs} depth (avg of 20)",
            f"{(time.perf_counter() - t0) / 20 * 1000:8.1f} ms")

        # ---- storm: 4 writers x msgs/4 into one chat, converge
        writers = [f"w{i}" for i in range(4)]
        for w in writers:
            bundles[w] = seed_account(tx, w)
        wmesh = {w: Mesh(FolderTransport(root), w, "soak",
                         home=(td / f"h-{w}"), encrypt=True) for w in writers}
        for w in writers:
            install_key(td / f"h-{w}", w, bundles[w])
        wmesh = {w: Mesh(FolderTransport(root), w, "soak",
                         home=(td / f"h-{w}"), encrypt=True) for w in writers}
        storm = owner.create_chat("Storm", members=writers)
        owner.outbox.flush_once()
        per = max(10, msgs // 4)
        t0 = time.perf_counter()

        def blast(w):
            m = wmesh[w]
            m.sync.sync_once([storm.id])
            for i in range(per):
                m.post(storm.id, f"{w} storm {i}")
            m.outbox.flush_once()

        ts = [threading.Thread(target=blast, args=(w,)) for w in writers]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        owner.sync.sync_once([storm.id])
        got = len([m for m in owner.messages_for(storm.id)
                   if m.kind.value == "message"])
        row(f"storm 4 writers x {per} (write+converge)",
            f"{(time.perf_counter() - t0):8.1f} s  ({got} msgs, "
            f"{'OK' if got == per * 4 else 'LOSS!'})")

        # ---- offline catch-up across breadth
        reader_home = td / "h-reader"
        bundles["reader"] = seed_account(tx, "reader")
        install_key(reader_home, "reader", bundles["reader"])
        breadth = []
        for i in range(chats):
            c = owner.create_chat(f"Wide {i}", members=["reader"])
            for j in range(msgs // chats):
                owner.post(c.id, f"wide {i}/{j}")
            breadth.append(c.id)
        owner.outbox.flush_once()
        reader = Mesh(FolderTransport(root), "reader", "soak",
                      home=reader_home, encrypt=True)
        t0 = time.perf_counter()
        reader.sync.sync_once(breadth)
        row(f"offline catch-up {chats} chats x {msgs // chats}",
            f"{time.perf_counter() - t0:8.1f} s")

        # ---- harness scan breadth (agents x rooms, no responder work)
        bots = [f"bot{i}" for i in range(agents)]
        for b in bots:
            bundles[b] = seed_account(tx, b, "agent", owner="aryan")
            install_key(home, b, bundles[b])
        rooms = []
        for i, b in enumerate(bots):
            r = owner.create_chat(f"Bot room {i}", members=[b])
            owner.post(r.id, f"hi @{b}")
            rooms.append(r.id)
        owner.outbox.flush_once()
        runners = [AgentRunner(root, b, home=home, machine="soak",
                               responder=Echo(), poll_s=0.2) for b in bots]
        t0 = time.perf_counter()

        def spin(r):
            r.mesh.sync.sync_once()
            r.tick()
            r.drain(timeout=120)
            r.mesh.outbox.flush_once()

        ts = [threading.Thread(target=spin, args=(r,)) for r in runners]
        for t in ts:
            t.start()
        for t in ts:
            t.join()
        answered = 0
        owner.sync.sync_once(rooms)
        for rid, b in zip(rooms, bots):
            answered += len([m for m in owner.messages_for(rid)
                             if m.from_ == b and m.kind.value == "message"])
        row(f"{agents} agents: sync+scan+reply (parallel)",
            f"{time.perf_counter() - t0:8.1f} s  ({answered}/{agents} replied)")
        for r in runners:
            r.close()

        # ---- cache rebuild
        t0 = time.perf_counter()
        fresh = Mesh(FolderTransport(root), "aryan", "soak2",
                     home=home, encrypt=True,
                     store_path=td / "fresh.sqlite")
        fresh.sync.sync_once()
        n = len(fresh.messages_for(c0.id))
        row("cache rebuild from transport (full root)",
            f"{time.perf_counter() - t0:8.1f} s  ({n} msgs in the deep chat)")
        fresh.close()
        reader.close()
        for m in wmesh.values():
            m.close()
        owner.close()
    finally:
        shutil.rmtree(td, ignore_errors=True)


class Echo:
    def respond(self, delivery, on_step=None):
        return Reply(body=f"ack from @{delivery.agent}")


def bench_supabase() -> None:
    from agentbridge.core.timekit import new_id
    from agentbridge.transport.supabase import SupabaseTransport, load_supabase_env

    env = load_supabase_env()
    if not env.get("SUPABASE_URL"):
        print("no supabase credentials — skipping")
        return
    root = f"soak-{new_id('r')[-8:]}"
    tx = SupabaseTransport(root, env=env)
    N = 40
    t0 = time.perf_counter()
    for i in range(N):
        tx.append_log("c1", "soak.jsonl", {"id": f"m{i}", "n": i})
    row(f"supabase append_log x {N} (serial)",
        f"{N / (time.perf_counter() - t0):8.1f} msg/s")
    t0 = time.perf_counter()
    recs, _ = tx.read_log("c1", "soak.jsonl", 0)
    row(f"supabase read_log {len(recs)} rows", f"{(time.perf_counter() - t0) * 1000:8.0f} ms")
    t0 = time.perf_counter()
    for i in range(10):
        tx.put_doc(f"docs/d{i}.json", {"i": i})
    row("supabase put_doc x 10", f"{(time.perf_counter() - t0) * 1000 / 10:8.0f} ms each")
    tx.delete_chat("c1")
    for p in tx.list_docs(""):
        tx.delete_doc(p)
    tx.close()
    print("  (cloud soak root cleaned)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", type=int, default=10)
    ap.add_argument("--chats", type=int, default=10)
    ap.add_argument("--msgs", type=int, default=200)
    ap.add_argument("--supabase", action="store_true")
    args = ap.parse_args()
    print(f"[soak] agents={args.agents} chats={args.chats} msgs={args.msgs}")
    if args.supabase:
        bench_supabase()
    else:
        bench_folder(args.agents, args.chats, args.msgs)
    print("[soak] done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
