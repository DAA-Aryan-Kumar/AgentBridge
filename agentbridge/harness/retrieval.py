"""Retrieval over chat history (R21) — long chats stop forgetting.

The context file carries the transcript TAIL; everything older is invisible
to the model. This module keeps a per-chat vector index of the FULL history
(fed from the read model, which reads the SQLite cache — membership-filtered
by construction) and pulls the few older messages that actually matter for
the current trigger into a "relevant earlier messages" context block.

The loop, per D21's plan: request → PLAN a query → search → rank → inject.
``plan_query`` is deliberately deterministic today (the trigger text + the
quoted parent) — it is the seam where a planner model slots in later without
touching anything around it (D11: extraction/planning LLMs are configurable
and local-first; this box has none, so nothing here requires one). True
prose summarization of old history is deferred with it — retrieval answers
the same "long chat" problem without a summarizer model.

Index mechanics: the collections live in the agent's ONE qdrant path
(``hist-<chat_id>``, next to R20's memory collections — local mode is
single-process per path, so everything shares the MemoryStore's client);
the per-chat high-water mark (``ns``) lives in the agent's SQLite store, so
re-index work is incremental and a wiped qdrant dir simply rebuilds.
"""

from __future__ import annotations

import threading
import uuid

from ..core.models import Message, MsgKind
from .memory import MemoryStore

__all__ = ["HistoryIndex", "plan_query"]

CURSOR_DOC = "harness/hist_cursor/{chat}"
MIN_SCORE = 0.30          # below this, "relevant" is noise — say nothing
MAX_RECALL = 6
_MAX_INDEX_TEXT = 1000


def plan_query(delivery) -> str:
    """The retrieval query for this run — THE planner seam (deterministic
    today: what was asked + what it replied to; a planner model later)."""
    parts = []
    for t in delivery.triggers:
        parts.append(t.message.body or "")
        rt = t.message.reply_to or {}
        if rt.get("body"):
            parts.append(rt["body"])
    return " ".join(" ".join(parts).split())[:800]


class HistoryIndex:
    """Incremental per-chat history index inside the agent's memory store."""

    def __init__(self, memory: MemoryStore, store=None) -> None:
        self.memory = memory
        self.store = store            # the agent's SQLite store (cursors)
        self._lock = threading.Lock()

    def available(self) -> bool:
        return self.memory.available()

    # ------------------------------------------------------------- indexing
    def ensure_indexed(self, chat_id: str, messages: list[Message]) -> int:
        """Embed everything newer than the high-water mark. Returns how many
        messages were added (0 on a quiet chat — the common case)."""
        name = f"hist-{chat_id}"
        with self._lock:
            last = int(self._cursor(chat_id))
            fresh = [m for m in messages
                     if m.ns > last and m.kind is MsgKind.MESSAGE
                     and not m.deleted and (m.body or m.files)]
            if not fresh:
                return 0
            self.memory._ensure_collection(name)
            from qdrant_client import models  # noqa: PLC0415

            texts = [self._index_text(m) for m in fresh]
            vectors = self.memory.embedder.embed(texts)
            self.memory._ensure_client().upsert(name, [
                models.PointStruct(
                    id=str(uuid.uuid4()), vector=vec,
                    payload={"msg_id": m.id, "text": text, "from": m.from_,
                             "ts": m.ts, "ns": m.ns})
                for m, text, vec in zip(fresh, texts, vectors)
            ])
            self._set_cursor(chat_id, max(m.ns for m in fresh))
            return len(fresh)

    @staticmethod
    def _index_text(m: Message) -> str:
        text = " ".join((m.body or "").split())[:_MAX_INDEX_TEXT]
        names = ", ".join(f.get("name", "") for f in (m.files or []))
        return f"{text} [files: {names}]" if names else text

    # ------------------------------------------------------------ retrieval
    def relevant(self, chat_id: str, query: str, *,
                 exclude_ids: set[str] | None = None,
                 k: int = MAX_RECALL) -> list[Message]:
        """The older messages worth re-reading for this query — never ones
        already visible in the transcript tail."""
        query = (query or "").strip()
        name = f"hist-{chat_id}"
        client = self.memory._ensure_client()
        if not query or not client.collection_exists(name):
            return []
        hits = client.query_points(
            name, query=self.memory.embedder.embed([query])[0],
            limit=k + len(exclude_ids or ()),
        ).points
        out = []
        for h in hits:
            p = h.payload or {}
            if float(h.score) < MIN_SCORE:
                continue
            if p.get("msg_id") in (exclude_ids or ()):
                continue
            out.append(Message(id=p.get("msg_id", ""), chat_id=chat_id,
                               from_=p.get("from", ""), ns=int(p.get("ns", 0)),
                               ts=p.get("ts", ""), body=p.get("text", "")))
            if len(out) >= k:
                break
        out.sort(key=lambda m: m.ns)      # read them in story order
        return out

    # ------------------------------------------------------------- plumbing
    def _cursor(self, chat_id: str) -> int:
        if self.store is None:
            return 0
        doc = self.store.cached_doc(CURSOR_DOC.format(chat=chat_id)) or {}
        return int(doc.get("ns", 0))

    def _set_cursor(self, chat_id: str, ns: int) -> None:
        if self.store is not None:
            self.store.cache_doc(CURSOR_DOC.format(chat=chat_id), {"ns": ns})
