"""The agent harness (R15) — successor to v1's ``agent_worker.py``.

One symmetric runner serves EVERY agent; per-agent differences live in the
owner-set harness config on the agent's account (``agent.harness``), never in
code. The harness is a Mesh-facade client like the GUI and the CLI: it never
reads the synced folder directly, so visibility = membership holds by
construction.

Core pieces:
- ``AgentRunner`` (runner.py): lifecycle, scan loop, dispatcher pool.
- ``WorkQueue`` (queue.py): durable trigger queue + the answered-guard.
- ``ConversationManager`` (conversation.py): enriched delivery bundles.
- ``PromptManager`` (prompt.py): every word the agent is told, from JSON.
- ``TimerService`` (timers.py): agent self-scheduled wake-ups, owner-visible.
- ``Responder`` (responder.py): the invocation seam R16's adapters implement.
"""

from .conversation import ConversationManager, Delivery, TriggerContext
from .prompt import PromptManager, PromptPack
from .responder import Reply, Responder, SILENCE, clean_reply
from .runner import AgentRunner, SingleInstance, main, supervise
from .settings import HarnessSettings
from .queue import WorkItem, WorkQueue
from .timers import TimerService

__all__ = [
    "AgentRunner", "ConversationManager", "Delivery", "HarnessSettings",
    "PromptManager", "PromptPack", "Reply", "Responder", "SILENCE",
    "SingleInstance", "TimerService", "TriggerContext", "WorkItem",
    "WorkQueue", "clean_reply", "main", "supervise",
]
