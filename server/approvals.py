# Synchronous approval gate for write tools (confirm-before-write).
"""Approvals: pause the agent loop until the phone user decides.

When the policy needs a human, we mint an approval id, push an
`approval_required` event to the session stream, and block the tool thread
until resolve() is called or the timeout fires.

Design rule: blocking is data. A timeout or rejection becomes a tool/policy
result string the model can read — never a server crash.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class ApprovalRequest:
    """One pending tool approval."""

    id: str
    call: dict
    reason: str
    created_at: float = field(default_factory=time.time)
    decision: str | None = None  # "approved" | "rejected" | None
    event: threading.Event = field(default_factory=threading.Event)

    def wait(self, timeout: float) -> str:
        """Block until decided. Returns approved | rejected | timeout."""
        if self.event.wait(timeout):
            return self.decision or "rejected"
        return "timeout"


class ApprovalGate:
    """Per-session gate used as Policy.approver and for explicit commit tools."""

    def __init__(
        self,
        timeout_s: float = 300.0,
        on_request: Callable[[ApprovalRequest], None] | None = None,
    ):
        self.timeout_s = timeout_s
        self.on_request = on_request or (lambda _req: None)
        self._lock = threading.Lock()
        self._pending: dict[str, ApprovalRequest] = {}

    def request(self, call: dict, reason: str) -> str:
        """Ask the user; return 'approved', 'rejected', or 'timeout'."""
        req = ApprovalRequest(id=str(uuid.uuid4()), call=call, reason=reason)
        with self._lock:
            self._pending[req.id] = req
        try:
            self.on_request(req)
            return req.wait(self.timeout_s)
        finally:
            with self._lock:
                self._pending.pop(req.id, None)

    def resolve(self, approval_id: str, approved: bool) -> bool:
        """Resolve a pending approval. Returns False if id is unknown."""
        with self._lock:
            req = self._pending.get(approval_id)
            if not req:
                return False
            req.decision = "approved" if approved else "rejected"
            req.event.set()
            return True

    def pending_snapshot(self) -> list[dict[str, Any]]:
        """List open approvals for debugging / GET endpoints."""
        with self._lock:
            return [
                {
                    "id": r.id,
                    "call": r.call,
                    "reason": r.reason,
                    "created_at": r.created_at,
                }
                for r in self._pending.values()
            ]

    def as_policy_approver(self):
        """Return a Policy-compatible approver(call, reason) -> bool."""

        def approver(call, reason):
            decision = self.request(call, reason)
            return decision == "approved"

        return approver
