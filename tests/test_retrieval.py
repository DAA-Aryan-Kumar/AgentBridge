"""History retrieval (R21): incremental indexing, relevance + tail
exclusion, the deterministic planner seam, and the context block."""

from __future__ import annotations

import pytest

pytest.importorskip("qdrant_client")

from agentbridge.core.models import Message  # noqa: E402
from agentbridge.harness import Delivery, HistoryIndex, MemoryStore, PromptManager  # noqa: E402
from agentbridge.harness.conversation import TriggerContext  # noqa: E402
from agentbridge.harness.retrieval import plan_query  # noqa: E402

from test_memory import fake_embedder  # noqa: E402


class FakeStore:
    def __init__(self):
        self.docs = {}

    def cache_doc(self, path, data):
        self.docs[path] = data

    def cached_doc(self, path, default=None):
        return self.docs.get(path, default)


def msg(i, body, files=None):
    return Message(id=f"m{i}", chat_id="c1", from_="aryan", ns=i,
                   ts=f"2026-07-13 10:{i:02d}", body=body, files=files or [])


@pytest.fixture
def index(tmp_path):
    store = MemoryStore(tmp_path / "mem", fake_embedder())
    idx = HistoryIndex(store, FakeStore())
    yield idx
    store.close()


def test_incremental_indexing_by_cursor(index):
    msgs = [msg(1, "the wifi password is hunter2 neon"),
            msg(2, "lunch plans for tuesday")]
    assert index.ensure_indexed("c1", msgs) == 2
    assert index.ensure_indexed("c1", msgs) == 0          # nothing new
    msgs.append(msg(3, "the deploy runs friday"))
    assert index.ensure_indexed("c1", msgs) == 1          # only the new one


def test_relevant_finds_old_and_excludes_the_tail(index):
    msgs = [msg(1, "the wifi password is hunter2 neon")]
    msgs += [msg(10 + i, f"filler chatter number {i}") for i in range(10)]
    index.ensure_indexed("c1", msgs)

    hits = index.relevant("c1", "what is the wifi password")
    assert hits and hits[0].id == "m1"
    assert "hunter2" in hits[0].body
    # the same message already visible in the tail is never re-surfaced
    assert index.relevant("c1", "what is the wifi password",
                          exclude_ids={"m1"}) == []
    # an unrelated query stays silent instead of dumping noise
    assert index.relevant("c1", "zebra xylophone quantum") == []


def test_relevant_orders_hits_in_story_order(index):
    index.ensure_indexed("c1", [
        msg(5, "deploy step two: run the migration"),
        msg(1, "deploy step one: freeze the branch"),
    ])
    hits = index.relevant("c1", "deploy step")
    assert [h.id for h in hits] == ["m1", "m5"]           # ns order, not score


def test_deleted_and_info_never_indexed(index):
    gone = msg(1, "secret before deletion")
    gone.deleted = True
    assert index.ensure_indexed("c1", [gone]) == 0


def test_plan_query_joins_trigger_and_quote():
    t = TriggerContext(
        message=Message(id="m9", body="what did we decide?",
                        reply_to={"from": "aryan", "body": "the color plan"}),
        reason="tagged", sender="aryan")
    d = Delivery(agent="helper", chat_id="c1", chat_name="Ops",
                 chat_kind="group", kind="message", rule="tagged",
                 triggers=[t])
    assert plan_query(d) == "what did we decide? the color plan"


def test_recalled_block_renders_before_the_tail(tmp_path):
    pack = PromptManager(tmp_path / "nohome").for_agent(None)
    d = Delivery(agent="helper", chat_id="c1", chat_name="Ops",
                 chat_kind="group", kind="message", rule="tagged",
                 roster=[], transcript=[msg(99, "newest message")],
                 recalled=[msg(1, "the wifi password is hunter2 neon")])
    text = pack.context_text(d)
    assert "found by search" in text
    assert text.index("hunter2") < text.index("The recent conversation")
    assert text.index("The recent conversation") < text.index("newest message")
