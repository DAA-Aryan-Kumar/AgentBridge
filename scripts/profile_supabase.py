"""Profile every SupabaseTransport op against the REAL project (R30).

Writes only under a throwaway root (default ``perfscratch``) and removes it
afterwards — the live mesh root is never touched. Rerunnable.

    uv run python scripts/profile_supabase.py [--n 20] [--root perfscratch]
                                              [--keep]

Prints p50/p95/max per operation plus the derived hot-path numbers (mirror
warm, idle sync tick).
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agentbridge.transport.cache import CachingTransport          # noqa: E402
from agentbridge.transport.supabase import SupabaseTransport      # noqa: E402

CHAT = "c-perf"


def timed(fn, n: int) -> list[float]:
    out = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t0) * 1000.0)
    return out


def row(name: str, samples: list[float]) -> str:
    p50 = statistics.median(samples)
    p95 = sorted(samples)[max(0, int(len(samples) * 0.95) - 1)]
    return f"  {name:<28} p50 {p50:7.1f} ms   p95 {p95:7.1f} ms   max {max(samples):7.1f} ms"


def cleanup(tx: SupabaseTransport) -> None:
    tx.delete_chat(CHAT)
    for path in tx.list_docs(""):
        tx.delete_doc(path)


def main() -> int:
    ap = argparse.ArgumentParser(description="Supabase transport profile")
    ap.add_argument("--root", default="perfscratch")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--docs", type=int, default=40,
                    help="how many docs the bulk/mirror reads sweep")
    ap.add_argument("--keep", action="store_true", help="skip the cleanup")
    args = ap.parse_args()

    tx = SupabaseTransport(args.root)
    print(f"profiling root '{args.root}' — {args.n} iterations/op")
    cleanup(tx)   # leftovers from an aborted earlier run

    n = args.n
    report: list[str] = []

    # ---- docs
    report.append(row("put_doc", timed(
        lambda: tx.put_doc(f"users/u{time.perf_counter_ns() % args.docs}.json",
                           {"name": "perf", "ns": time.time_ns()}), n)))
    for i in range(args.docs):   # a stable population for the read sweeps
        tx.put_doc(f"users/u{i}.json", {"name": f"perf{i}"})
    report.append(row("get_doc", timed(
        lambda: tx.get_doc("users/u1.json"), n)))
    report.append(row(f"get_docs (bulk, {args.docs} docs)", timed(
        lambda: tx.get_docs(""), max(5, n // 4))))
    report.append(row("list_docs", timed(lambda: tx.list_docs("users"), n)))

    # ---- logs
    report.append(row("append_log", timed(
        lambda: tx.append_log(CHAT, "perf@box.jsonl",
                              {"id": "m", "from": "perf",
                               "ns": time.time_ns()}), n)))
    offset = 0

    def read_new():
        nonlocal offset
        _, offset = tx.read_log(CHAT, "perf@box.jsonl", offset)

    report.append(row("read_log (incremental)", timed(read_new, n)))
    report.append(row("list_logs (1 chat)", timed(lambda: tx.list_logs(CHAT), n)))
    report.append(row("list_chat_ids (RPC)", timed(tx.list_chat_ids, n)))
    cursor = 0

    def feed():
        nonlocal cursor
        _, cursor = tx.changed_logs(cursor)

    feed()   # first call walks the backlog; the loop measures idle ticks
    report.append(row("changed_logs (idle tick)", timed(feed, n)))

    # ---- blobs
    blob = b"x" * 32_768
    report.append(row("put_blob (32 KB)", timed(
        lambda: tx.put_blob(f"chats/{CHAT}/files/perf.bin", blob),
        max(5, n // 4))))
    report.append(row("get_blob (32 KB)", timed(
        lambda: tx.get_blob(f"chats/{CHAT}/files/perf.bin"),
        max(5, n // 4))))

    # ---- the derived hot paths
    mirror = CachingTransport(tx, auto_refresh=False)
    t0 = time.perf_counter()
    mirror.refresh()
    warm_ms = (time.perf_counter() - t0) * 1000.0
    report.append(row("mirror warm (bulk+ids)", [warm_ms]))
    report.append(row("mirror get_doc (RAM)", timed(
        lambda: mirror.get_doc("users/u1.json"), n)))

    print("\n".join(report))
    print(f"\nidle sync tick: 1×changed_logs vs {1}×list_chat_ids + "
          f"N×list_logs on the per-chat path")
    if not args.keep:
        cleanup(tx)
        print("scratch root cleaned up")
    return 0


if __name__ == "__main__":
    sys.exit(main())
