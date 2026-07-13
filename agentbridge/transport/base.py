"""Transport interface — the ONLY layer that touches bytes-at-rest.

A transport moves the logical records of docs/FORMAT2.md over some shared
storage. Drivers: ``folder`` (OneDrive/Drive/SharePoint synced folder — files)
today, ``supabase`` (tables + storage + realtime) in R23. Everything above
this layer is storage-agnostic.

Contract highlights (the parts that make a sync transport reliable):
- ``put_doc`` is ATOMIC and retries transient locks; readers never see half a
  document. ``get_doc`` tolerates missing/corrupt (returns default).
- ``append_log`` appends exactly one record; ``read_log`` is INCREMENTAL by
  opaque offset and only advances past COMPLETE records (a half-synced line is
  left for a later pass; a shrunken file resets the offset — callers dedup by
  record id).
- ``watch()`` returns a HINT-only watcher: it may wake early on changes but
  the caller's timed rescan remains the source of truth (FORMAT2 tenet 6).
- Paths are POSIX-style, RELATIVE, and validated — a transport must refuse
  any path that escapes its root.

Adding a connector = subclass Transport, implement the abstract methods, and
register the scheme in ``make_transport``. The REQUIRED surface is enough for
full correctness; two OPTIONAL fast paths make a high-RTT (cloud) driver feel
local, and both degrade gracefully when absent:
- ``get_docs(prefix)`` — bulk-read every doc in one round-trip. The default
  loops ``list_docs``+``get_doc`` (fine locally, slow over a network); a cloud
  driver should override it with one query. The mirror cache (cache.py) warms
  and refreshes from this.
- ``changed_logs(cursor)`` + ``has_change_feed = True`` — a global,
  monotonic change feed over the message logs ("which (chat, log) have rows
  newer than this opaque cursor?"). Lets the sync engine poll ALL chats in
  one round-trip instead of listing logs per chat. Leave ``has_change_feed``
  False (the default) and the sync engine sticks to the per-chat scan.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

__all__ = ["Transport", "Watcher"]


class Watcher:
    """Best-effort change hint. ``wait`` blocks up to ``timeout`` seconds and
    returns True if a change was hinted (clearing the hint). The default
    implementation never hints — pure polling."""

    def wait(self, timeout: float) -> bool:
        import time

        time.sleep(timeout)
        return False

    def close(self) -> None:  # pragma: no cover - trivial
        pass


class Transport(ABC):
    scheme: str = "abstract"

    # Ceiling is a property of the TRANSPORT, not the app: a synced folder
    # pushes every attachment to each member's machine; an API store has its
    # own service limits. The GUI names this limit in the too-large dialog.
    max_upload_bytes: int = 512 * 1024 * 1024

    # ------------------------------------------------------------------ docs
    @abstractmethod
    def get_doc(self, path: str, default: Any = None) -> Any:
        """JSON document at ``path``; missing/corrupt -> ``default``."""

    @abstractmethod
    def put_doc(self, path: str, data: Any) -> None:
        """Atomically replace the document (creating parents)."""

    @abstractmethod
    def delete_doc(self, path: str) -> None:
        """Remove a document; missing is not an error."""

    @abstractmethod
    def list_docs(self, prefix: str) -> list[str]:
        """Paths of ``.json`` documents under ``prefix`` (recursive)."""

    def get_docs(self, prefix: str = "") -> dict[str, Any]:
        """OPTIONAL fast path: every doc under ``prefix`` at once. This
        default loops the required methods (fine on a local driver); a cloud
        driver should override it with ONE bulk query — the mirror cache
        warms from it. Unlike ``get_doc`` this may RAISE on failure, so the
        caller can tell "store is empty" apart from "network is down"."""
        _absent = object()
        out: dict[str, Any] = {}
        for path in self.list_docs(prefix):
            value = self.get_doc(path, _absent)
            if value is not _absent:
                out[path] = value
        return out

    # ----------------------------------------------------------- chats / logs
    @abstractmethod
    def list_chat_ids(self) -> list[str]: ...

    # OPTIONAL fast path: a driver with a global, monotonic change feed over
    # its logs sets this True and overrides changed_logs — the sync engine
    # then polls every chat in ONE round-trip instead of listing logs per chat
    has_change_feed: bool = False

    def changed_logs(self, cursor: int) -> tuple[list[tuple[str, str]], int]:
        """``(chat_id, log_name)`` pairs holding records newer than the opaque
        ``cursor``, plus the new cursor (pass 0 for "everything"). Only called
        when ``has_change_feed`` is True. May RAISE on failure — the caller
        retries with the same cursor next tick."""
        raise NotImplementedError(f"{type(self).__name__} has no change feed")

    @abstractmethod
    def list_logs(self, chat_id: str) -> list[tuple[str, int]]:
        """``(log_name, size)`` for every message log of the chat. ``size``
        is an opaque change indicator (file bytes / row high-water)."""

    @abstractmethod
    def append_log(self, chat_id: str, log_name: str, record: dict) -> None:
        """Append ONE record to the (single-writer, per-device) log."""

    @abstractmethod
    def read_log(
        self, chat_id: str, log_name: str, offset: int = 0
    ) -> tuple[list[dict], int]:
        """Records after ``offset`` plus the new offset. Only complete,
        parseable records are returned; the offset never lands mid-record."""

    @abstractmethod
    def delete_chat(self, chat_id: str) -> None:
        """Remove a chat subtree (admin-gated far above this layer)."""

    # ----------------------------------------------------------------- blobs
    @abstractmethod
    def put_blob(self, path: str, data: bytes) -> None: ...

    @abstractmethod
    def put_blob_from(self, local_src: Path, path: str) -> None:
        """Copy a LOCAL file into the store (attachments inbound)."""

    @abstractmethod
    def get_blob(self, path: str) -> bytes | None: ...

    @abstractmethod
    def blob_size(self, path: str) -> int | None: ...

    def local_path(self, path: str) -> Path | None:
        """Real filesystem path for folder-backed stores, else None — the seam
        where open-with-OS / preview features degrade for API backends."""
        return None

    # ---------------------------------------------------------------- events
    def watch(self) -> Watcher:
        """A change-hint watcher (default: pure polling)."""
        return Watcher()
