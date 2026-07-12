"""mesh-cli v2: the MCP server surface + human-mode commands (R12).

``build_mcp`` lives in ``.server`` and needs the optional ``mcp`` extra —
import it from there directly; this package stays importable core-only.
"""

from .main import main

__all__ = ["main"]
