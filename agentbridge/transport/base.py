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

    # ----------------------------------------------------------- chats / logs
    @abstractmethod
    def list_chat_ids(self) -> list[str]: ...

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
