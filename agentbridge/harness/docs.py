"""Tool documentation (R43, Q7/Q11) — one data file owns every per-tool word.

``prompts/tooldocs.json`` carries, per tool: the ``ask`` verb phrase the
owner's permission popup shows ("wants to write a file", never a raw tool
id), the ``short`` one-liner, and the ``long`` manual entry; plus ``guides``
— conceptual entries (workspace, memory, etiquette, …). The bridge's
``read_docs`` tool serves the catalog and the entries, so the run prompt
stays lean (Q7: documentation is a tool, not inline context) and an agent
can quote its own manual when a member asks what it can do (Q11).

Resolution mirrors the prompt pack: the shipped file, overlaid by
``<home>/prompts/tooldocs.json`` — an owner rewords or extends entries
without touching code.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from ..core.config import DEFAULT_HOME
from .prompt import _friendly_tool_name

__all__ = ["ToolDocs"]

PACK_FILE = Path(__file__).resolve().parent / "prompts" / "tooldocs.json"

_PART_KEY_RE = re.compile(r"\{(\w+)\}")
_DETAIL_VAL_MAX = 120


def _human_secs(seconds: float) -> str:
    """5 -> '5s', 300 -> '5 min', 7200 -> '2 h' — the popup's timeout unit."""
    if seconds < 90:
        return f"{seconds:g}s"
    if seconds < 5400:
        return f"{round(seconds / 60)} min"
    return f"{round(seconds / 3600)} h"


def _detail_fill(tool_input: dict) -> dict[str, str]:
    """The template's key space: every scalar input value as a compact
    single-line string, plus a derived ``{timeout}`` humanized from the
    explicit timeout CC-style tools carry (``timeout_ms``/``timeout_s``;
    a bare ``timeout`` >= 1000 reads as milliseconds — CC's Bash unit)."""
    fill: dict[str, str] = {}
    for k, v in (tool_input or {}).items():
        if isinstance(v, (dict, list)) or v is None or isinstance(v, bool):
            continue  # structures/flags don't read well on one line
        fill[str(k)] = " ".join(str(v).split())[:_DETAIL_VAL_MAX]
    for key, scale in (("timeout_ms", 1000.0), ("timeout_s", 1.0)):
        v = (tool_input or {}).get(key)
        if isinstance(v, (int, float)) and v > 0:
            fill.setdefault("timeout", _human_secs(v / scale))
    v = (tool_input or {}).get("timeout")
    if isinstance(v, (int, float)) and v > 0:
        fill["timeout"] = _human_secs(v / 1000.0 if v >= 1000 else float(v))
    return fill


def _load_json(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


class ToolDocs:
    def __init__(self, data: dict) -> None:
        self.tools: dict[str, dict] = {
            str(k).lower(): v for k, v in (data.get("tools") or {}).items()
            if isinstance(v, dict)
        }
        self.guides: dict[str, dict] = {
            str(k).lower(): v for k, v in (data.get("guides") or {}).items()
            if isinstance(v, dict)
        }

    @classmethod
    def load(cls, home: Path | None = None) -> "ToolDocs":
        """Shipped entries, overlaid per-section by the home file (an
        override replaces a tool's whole entry, never merges inside it —
        partial entries would silently drop the fields they omit)."""
        data = _load_json(PACK_FILE)
        override = _load_json((home or DEFAULT_HOME) / "prompts" / "tooldocs.json")
        for section in ("tools", "guides"):
            merged = dict(data.get(section) or {})
            merged.update(override.get(section) or {})
            data[section] = merged
        return cls(data)

    # -------------------------------------------------------------- ask lane
    def ask_phrase(self, tool: str) -> str:
        """The popup's verb phrase for a tool — 'write a file' — falling back
        to a humanized name ('use search issues (github)') so a raw tool id
        never reaches the owner."""
        entry = self.tools.get(str(tool or "").lower())
        phrase = str((entry or {}).get("ask") or "").strip()
        if phrase:
            return phrase
        return f"use {_friendly_tool_name(tool)}" if tool else ""

    def detail_phrase(self, tool: str, tool_input: dict) -> str:
        """The popup's DETAIL line for a non-path tool call (V86): the
        entry's ``detail`` template(s) over the call's input — "background
        work · up to 5s" beats the raw input JSON the popup used to print.
        ``detail`` is a string or a list of PARTS; a part renders only when
        every ``{key}`` it names resolves non-empty, and the surviving parts
        join with ' · '. Returns '' when nothing renders — the broker keeps
        the raw-JSON fallback (friendly for the common tools via config,
        honest JSON for the rest)."""
        entry = self.tools.get(str(tool or "").lower())
        spec = (entry or {}).get("detail")
        parts = [spec] if isinstance(spec, str) else list(spec or [])
        fill = _detail_fill(tool_input or {})
        out = []
        for part in parts:
            part = str(part)
            keys = _PART_KEY_RE.findall(part)
            if not keys or not all(fill.get(k) for k in keys):
                continue
            try:
                out.append(part.format(**{k: fill[k] for k in keys}))
            except (KeyError, IndexError, ValueError):
                continue  # a malformed template part never breaks an ask
        return " · ".join(out)

    # ------------------------------------------------------------- docs lane
    def catalog(self) -> str:
        """read_docs() — the table of contents: every guide and documented
        tool with its one-liner."""
        lines = ["Your AgentBridge manual. Call read_docs(<name>) for any "
                 "entry below.", "", "Guides:"]
        for name, g in sorted(self.guides.items()):
            lines.append(f"- {name}: {str(g.get('short') or '').strip()}")
        lines.append("")
        lines.append("Tools:")
        for name, t in sorted(self.tools.items()):
            short = str(t.get("short") or "").strip()
            if short:  # inner-CLI tools carry only an ask phrase — not yours
                lines.append(f"- {name}: {short}")
        return "\n".join(lines)

    def topic(self, name: str) -> str:
        """read_docs(name) — the full entry for a guide or tool. Accepts the
        bare name or the mcp-prefixed spelling."""
        key = str(name or "").strip().lower()
        if key.startswith("mcp__"):
            key = key.split("__")[-1]
        entry = self.guides.get(key) or self.tools.get(key)
        if entry:
            body = str(entry.get("long") or entry.get("short") or "").strip()
            if body:
                return body
        near = [k for k in [*self.guides, *self.tools] if key and key in k]
        hint = f" Did you mean: {', '.join(sorted(near))}?" if near else ""
        return (f"No entry named {key!r}.{hint} Call read_docs() with no "
                f"argument for the full list.")
