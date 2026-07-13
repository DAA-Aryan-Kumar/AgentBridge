"""Agent memory (R20) — a local vector store the agent reaches through its
bridge tools, never a cloud service.

Two tiers, deliberately simple until R21's retrieval round:
- the WORKSPACE note file (``MEMORY.md``): plain text inside the agent's
  per-chat desk, read/written freely — no tools, no ceremony;
- the VECTOR store (this module): ``remember``/``recall`` bridge tools over
  qdrant in **local mode** under the agent's home. One qdrant path per agent
  PROCESS (local mode is single-process by design — portalocker), with one
  collection per chat plus one ``global`` collection. Chat memory stays
  scoped to its chat; global memory follows the owner's policy
  (``global_memory``: dm | everywhere | off — default dm, so a group chat
  can't quietly write into an agent's cross-chat brain).

Embeddings ride a PROBE CHAIN behind our own interface (D15): fastembed
(onnxruntime — blocked on some corporate Windows boxes) → model2vec
(potion-base-8M, pure numpy — the verified fallback on the dev box). The
chain is probed at first use, never at import; a box with neither simply
reports memory as unavailable instead of breaking the harness. mem0-style
entity extraction (D16) waits for a box with an extraction LLM.
"""

from __future__ import annotations

import threading
import time
import uuid
from pathlib import Path

__all__ = ["Embedder", "MemoryStore", "probe_backends"]

GLOBAL = "global"
_MAX_TEXT = 2000


# ------------------------------------------------------------- embeddings
def _load_fastembed():
    from fastembed import TextEmbedding  # noqa: PLC0415 — probe-time import

    model = TextEmbedding("BAAI/bge-small-en-v1.5")

    def embed(texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in model.embed(texts)]

    return "fastembed/bge-small-en-v1.5", 384, embed


def _load_model2vec():
    from model2vec import StaticModel  # noqa: PLC0415 — probe-time import

    model = StaticModel.from_pretrained("minishlab/potion-base-8M")

    def embed(texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in model.encode(texts)]

    return "model2vec/potion-base-8M", 256, embed


PROBE_CHAIN = (_load_fastembed, _load_model2vec)


def probe_backends(chain=PROBE_CHAIN):
    """First loadable backend wins; None when the box has none."""
    for loader in chain:
        try:
            return loader()
        except Exception:  # noqa: BLE001 — a missing backend is normal
            continue
    return None


class Embedder:
    """Lazy, thread-safe wrapper over the probe chain (models load once)."""

    def __init__(self, chain=PROBE_CHAIN) -> None:
        self._chain = chain
        self._lock = threading.Lock()
        self._loaded = False
        self._backend = None

    def available(self) -> bool:
        self._ensure()
        return self._backend is not None

    @property
    def id(self) -> str:
        self._ensure()
        return self._backend[0] if self._backend else ""

    @property
    def dim(self) -> int:
        self._ensure()
        return self._backend[1] if self._backend else 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self._ensure()
        if self._backend is None:
            raise RuntimeError("no embedding backend is available")
        return self._backend[2](texts)

    def _ensure(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if not self._loaded:
                self._backend = probe_backends(self._chain)
                self._loaded = True


# ------------------------------------------------------------ vector store
class MemoryStore:
    """qdrant-local memories for ONE agent. Collections: per chat + global."""

    def __init__(self, path: Path | str, embedder: Embedder | None = None) -> None:
        self.path = Path(path)
        self.embedder = embedder or Embedder()
        self._lock = threading.Lock()
        self._client = None

    # ------------------------------------------------------------- plumbing
    def available(self) -> bool:
        if not self.embedder.available():
            return False
        try:
            self._ensure_client()
            return True
        except Exception:  # noqa: BLE001 — no qdrant = no memory, not a crash
            return False

    def _ensure_client(self):
        if self._client is None:
            with self._lock:
                if self._client is None:
                    from qdrant_client import QdrantClient  # noqa: PLC0415

                    self.path.mkdir(parents=True, exist_ok=True)
                    self._client = QdrantClient(path=str(self.path))
        return self._client

    def _collection(self, scope: str, chat_id: str) -> str:
        return GLOBAL if scope == GLOBAL else f"chat-{chat_id}"

    def _ensure_collection(self, name: str) -> None:
        from qdrant_client import models  # noqa: PLC0415

        client = self._ensure_client()
        if not client.collection_exists(name):
            client.create_collection(
                name,
                vectors_config=models.VectorParams(
                    size=self.embedder.dim,
                    distance=models.Distance.COSINE),
            )

    # ---------------------------------------------------------------- API
    def remember(self, *, scope: str, chat_id: str, text: str,
                 by: str = "") -> str:
        text = " ".join((text or "").split())[:_MAX_TEXT]
        if not text:
            raise ValueError("nothing to remember")
        name = self._collection(scope, chat_id)
        self._ensure_collection(name)
        from qdrant_client import models  # noqa: PLC0415

        pid = str(uuid.uuid4())
        self._ensure_client().upsert(name, [models.PointStruct(
            id=pid, vector=self.embedder.embed([text])[0],
            payload={"text": text, "by": by, "chat_id": chat_id,
                     "ts": time.time(), "embedder": self.embedder.id},
        )])
        return pid

    def recall(self, *, scope: str, chat_id: str, query: str,
               limit: int = 5) -> list[dict]:
        name = self._collection(scope, chat_id)
        client = self._ensure_client()
        if not client.collection_exists(name):
            return []
        hits = client.query_points(
            name, query=self.embedder.embed([query])[0],
            limit=max(1, min(int(limit), 20)),
        ).points
        return [{"text": (h.payload or {}).get("text", ""),
                 "score": round(float(h.score), 3),
                 "ts": (h.payload or {}).get("ts")} for h in hits]

    def close(self) -> None:
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
