"""One-shot migration: copy a synced-folder mesh into a Supabase project.

COPY, not move — the source folder is left fully intact, so switching the live
mesh to Supabase stays reversible (point config.json back at the folder if
anything is off). Idempotent: docs + blobs upsert; logs are skipped for any
(chat, log) that already has rows on the destination, so a re-run never
duplicates message lines.

    uv run python scripts/migrate_folder_to_supabase.py [--root mesh2] [--dry-run]

Source folder is read from ~/.agentbridge/config.json (`mesh_root`); the
destination is `supabase://<root>` (default root name `mesh2`, matching the
folder). Credentials come from ~/.agentbridge/supabase.env (R23).
"""

from __future__ import annotations

import argparse
import glob
import os
from pathlib import Path

from agentbridge.core.config import DEFAULT_HOME, load_app_config
from agentbridge.transport import FolderTransport, make_transport


def _blob_rel_paths(folder_root: Path) -> list[str]:
    """Every non-doc file in the folder (blobs): attachments + avatars. Docs
    are .json, logs are .jsonl — everything else rides the blob channel."""
    out: list[str] = []
    for dp, _dirs, files in os.walk(folder_root):
        for f in files:
            if f.endswith((".json", ".jsonl")):
                continue
            full = Path(dp) / f
            out.append(full.relative_to(folder_root).as_posix())
    return sorted(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="mesh2", help="destination supabase root name")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_app_config(None)
    src_root = cfg.get("mesh_root")
    if not src_root or "://" in str(src_root):
        raise SystemExit(f"config mesh_root is not a folder: {src_root!r}")
    folder_root = Path(src_root)
    src = FolderTransport(folder_root)
    dst = make_transport(f"supabase://{args.root}", home=DEFAULT_HOME)

    print(f"source : {folder_root}")
    print(f"dest   : supabase://{args.root}")
    print(f"dry-run: {args.dry_run}\n")

    # 1) docs (upsert — idempotent)
    docs = src.list_docs("")
    print(f"docs: {len(docs)}")
    for p in docs:
        data = src.get_doc(p)
        if data is None:
            continue
        if not args.dry_run:
            dst.put_doc(p, data)
        print(f"  doc  {p}")

    # 2) logs (skip any (chat, log) that already has rows on the dest)
    n_logs = n_records = 0
    for chat in src.list_chat_ids():
        existing = {name for name, head in dst.list_logs(chat) if head > 0}
        for log_name, _size in src.list_logs(chat):
            if log_name in existing:
                print(f"  log  {chat}/{log_name}  SKIP (already present)")
                continue
            records, _ = src.read_log(chat, log_name, 0)
            n_logs += 1
            for rec in records:
                n_records += 1
                if not args.dry_run:
                    dst.append_log(chat, log_name, rec)
            print(f"  log  {chat}/{log_name}  ({len(records)} records)")
    print(f"logs: {n_logs} files, {n_records} records")

    # 3) blobs (upsert — idempotent)
    blobs = _blob_rel_paths(folder_root)
    print(f"blobs: {len(blobs)}")
    for rel in blobs:
        data = src.get_blob(rel)
        if data is None:
            continue
        if not args.dry_run:
            dst.put_blob(rel, data)
        print(f"  blob {rel}  ({len(data)} bytes)")

    print("\nDONE." + ("  (dry run — nothing written)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
