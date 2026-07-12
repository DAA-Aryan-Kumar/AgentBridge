"""The GUI connector (R13) — a thin local HTTP server over the Mesh facade.

Serves the vanilla-ES-module frontend (``gui/static/``) plus a JSON API that
is shape-compatible with the v1 endpoints where sane, and adds the v2
surfaces: SSE off the event bus, privacy matrix, status/about, admins &
group permissions, handle/password change. Binds to 127.0.0.1 only — this
is a local app, not a network service.

Every read and write goes through the facade; nothing here reaches past it
to the transport. Errors surface as ``{"error": ...}`` JSON (the v1 client
contract) — never as HTML error pages.
"""

from .app import main  # noqa: F401

__all__ = ["main"]
