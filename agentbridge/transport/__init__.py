"""Transport layer: the only code that touches bytes-at-rest (FORMAT2)."""

from pathlib import Path

from .base import Transport, Watcher
from .folder import FolderTransport

__all__ = ["Transport", "Watcher", "FolderTransport", "make_transport"]


def make_transport(spec, home: Path | None = None) -> Transport:
    """One factory for every driver: a ``supabase://<root-name>`` spec builds
    the cloud driver (credentials from ``<home>/supabase.env``, R23);
    anything else is a synced-folder path. Callers keep passing whatever the
    remembered config holds — the scheme decides."""
    if isinstance(spec, Transport):
        return spec
    text = str(spec)
    if text.startswith("supabase://"):
        from .supabase import SupabaseTransport

        return SupabaseTransport(text[len("supabase://"):], home=home)
    return FolderTransport(spec)
