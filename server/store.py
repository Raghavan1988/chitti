# In-memory session registry keyed by public session ids.
"""Session store: maps API session ids to MobileHarness instances.

Each phone conversation gets a harness, an event queue for SSE, and its own
approval gate. Disk persistence of messages is still handled by Odysseus
session JSONL under the workspace.
"""

from __future__ import annotations

import queue
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any

from .approvals import ApprovalGate
from .config import config
from .mobile_harness import MobileHarness


@dataclass
class LiveSession:
    """One active mobile conversation."""

    id: str
    harness: MobileHarness
    events: queue.Queue = field(default_factory=queue.Queue)
    lock: threading.Lock = field(default_factory=threading.Lock)
    running: bool = False
    last_error: str | None = None

    def push(self, kind: str, payload: Any):
        self.events.put({"kind": kind, "payload": payload})

    def close_stream(self):
        self.events.put(None)  # sentinel for SSE consumers


class SessionStore:
    """Process-wide registry of live sessions."""

    def __init__(self):
        self._lock = threading.Lock()
        self._sessions: dict[str, LiveSession] = {}

    def create(self, label: str = "mobile") -> LiveSession:
        sid = str(uuid.uuid4())
        live = LiveSession(id=sid, harness=None)  # type: ignore

        def on_event(kind, payload):
            live.push(kind, payload)

        gate = ApprovalGate(
            timeout_s=config.approval_timeout_s,
            on_request=lambda req: live.push(
                "approval_required",
                {"id": req.id, "call": req.call, "reason": req.reason},
            ),
        )
        harness = MobileHarness(
            workdir=str(config.workdir),
            on_event=on_event,
            gate=gate,
            persist=True,
        )
        harness.ensure_session(label)
        live.harness = harness
        with self._lock:
            self._sessions[sid] = live
        live.push("session", {"id": sid, "session_path": harness.session_path})
        return live

    def get(self, sid: str) -> LiveSession | None:
        with self._lock:
            return self._sessions.get(sid)

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())


store = SessionStore()
