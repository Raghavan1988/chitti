# SignalLoop core: durable loops + idempotent command bus (no AppIntents).
"""LoopEngine — the source of truth for SignalLoop loops.

Every surface (SwiftUI, Siri App Intent adapter, Share sheet, widget,
notification action, cloud wake) submits a **LoopCommand** to one engine. The
engine is the only place that mutates loop state, so planning and policy never
leak into adapters (plan.md §2, AGENTS.md invariants).

Design rules encoded here:

- **Idempotency is a contract.** Every command carries ``source`` +
  ``idempotency_key``; replaying a key returns the first result and never
  duplicates a loop, evidence item, or externalized action.
- **No silent externalize.** Drafts are safe to create. Sending / posting /
  committing a draft (``externalize``) requires a ``review_token`` minted by an
  authenticated foreground review (``resolve_review``). A missing or invalid
  token is a *safe refusal*, not a crash and not a silent send.
- **Core isolation.** This module depends only on the stdlib + ``config``. It
  imports no HTTP framework and (being Python) no AppIntents; the HTTP layer in
  ``app.py`` is a thin transport over ``engine.apply``.

Persistence is a single JSON document under ``workdir/.chitti/loops.json``,
written atomically so loops survive a server restart.
"""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any

from .config import config

# --- vocabularies (plan.md §3/§4) -------------------------------------------

SOURCES = {"siri", "app", "share", "widget", "notification", "cloud_wake"}
DOMAINS = {"career", "life", "both"}
STATUSES = {"active", "waiting", "blocked", "paused", "done"}

# Command types accepted by the bus. Each has an in-app twin (plan.md §4).
COMMAND_TYPES = {
    "new_loop",
    "update_loop",
    "log_evidence",
    "add_draft",
    "delete_draft",
    "pause",
    "resume",
    "approve_plan",
    "mark_complete",
    "request_review",
    "resolve_review",
    "externalize",
    "remember",
    "clear_suggestions",
}


class CommandError(Exception):
    """A malformed command the caller should fix (maps to HTTP 400).

    Safe *refusals* (e.g. externalize without a review token) are NOT errors —
    they return a normal result with an explanation so the model/UI can react.
    """


def _now() -> float:
    return time.time()


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# --- data model (plan.md §3) ------------------------------------------------


@dataclass
class Loop:
    """One open loop the user is trying to advance (career | life | both)."""

    id: str
    title: str
    domain: str = "career"
    status: str = "active"
    why_it_matters: str = ""
    next_action: str = ""
    waiting_until: str | None = None
    outcome: str | None = None
    plan_approved: bool = False
    evidence: list[dict] = field(default_factory=list)
    steps: list[dict] = field(default_factory=list)
    blockers: list[dict] = field(default_factory=list)
    drafts: list[dict] = field(default_factory=list)
    links: list[dict] = field(default_factory=list)
    log: list[dict] = field(default_factory=list)
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)


@dataclass
class Review:
    """A pending consequential-action review that gates externalization.

    ``token`` is minted only when an authenticated foreground review approves
    the action; ``externalize`` consumes exactly one approved, unused token.
    """

    id: str
    loop_id: str
    action: str
    draft_id: str | None = None
    status: str = "pending"  # pending | approved | rejected
    token: str | None = None
    consumed: bool = False
    created_at: float = field(default_factory=_now)
    resolved_at: float | None = None


@dataclass
class LoopCommand:
    """A single intent submitted to the bus by any surface."""

    type: str
    payload: dict = field(default_factory=dict)
    source: str = "app"
    idempotency_key: str = ""

    @classmethod
    def from_dict(cls, body: dict) -> "LoopCommand":
        if not isinstance(body, dict):
            raise CommandError("command must be a JSON object")
        ctype = body.get("type")
        if ctype not in COMMAND_TYPES:
            raise CommandError(f"unknown command type: {ctype!r}")
        source = body.get("source", "app")
        if source not in SOURCES:
            raise CommandError(f"unknown source: {source!r}")
        key = (body.get("idempotency_key") or "").strip()
        if not key:
            raise CommandError("idempotency_key is required")
        payload = body.get("payload") or {}
        if not isinstance(payload, dict):
            raise CommandError("payload must be a JSON object")
        return cls(type=ctype, payload=payload, source=source, idempotency_key=key)


# --- engine -----------------------------------------------------------------


class LoopEngine:
    """Durable, thread-safe, idempotent command processor for loops."""

    def __init__(self, path: str | os.PathLike | None = None):
        self._lock = threading.RLock()
        self._path = (
            os.fspath(path)
            if path is not None
            else str(config.workdir / ".chitti" / "loops.json")
        )
        self._loops: dict[str, Loop] = {}
        self._reviews: dict[str, Review] = {}
        self._facts: list[dict] = []  # global memory (durable prefs/facts)
        self._idem: dict[str, dict] = {}  # idempotency_key -> stored result
        self._load()

    # -- persistence --

    def _load(self) -> None:
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return
        self._loops = {k: Loop(**v) for k, v in data.get("loops", {}).items()}
        self._reviews = {k: Review(**v) for k, v in data.get("reviews", {}).items()}
        self._facts = list(data.get("facts", []))
        self._idem = dict(data.get("idempotency", {}))

    def _save(self) -> None:
        data = {
            "loops": {k: asdict(v) for k, v in self._loops.items()},
            "reviews": {k: asdict(v) for k, v in self._reviews.items()},
            "facts": self._facts,
            "idempotency": self._idem,
        }
        directory = os.path.dirname(self._path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        tmp = f"{self._path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self._path)  # atomic on POSIX

    # -- public reads --

    def list_loops(self) -> list[dict]:
        with self._lock:
            loops = sorted(
                self._loops.values(), key=lambda x: x.updated_at, reverse=True
            )
            return [asdict(x) for x in loops]

    def get_loop(self, loop_id: str) -> dict | None:
        with self._lock:
            loop = self._loops.get(loop_id)
            return asdict(loop) if loop else None

    def seen(self, idempotency_key: str) -> bool:
        """True if this idempotency key has already produced a recorded effect.

        Lets server-layer callers (e.g. the suggester) skip redoing expensive
        work — like a model call — when a per-day command was already applied.
        """
        with self._lock:
            return idempotency_key in self._idem

    def list_reviews(self, pending_only: bool = True) -> list[dict]:
        with self._lock:
            revs = self._reviews.values()
            if pending_only:
                revs = [r for r in revs if r.status == "pending"]
            return [asdict(r) for r in revs]

    def facts(self) -> list[dict]:
        with self._lock:
            return list(self._facts)

    def status_board(self, locked: bool = False) -> dict:
        """Return a status projection for the Status surface.

        ``locked=True`` yields a **privacy-safe** projection with no titles,
        evidence, or draft content — only counts by domain/status (plan.md §4
        "Status privacy"). Never speak sensitive content from the lock screen.
        """
        with self._lock:
            loops = list(self._loops.values())
            by_status: dict[str, int] = {}
            by_domain: dict[str, int] = {}
            for loop in loops:
                by_status[loop.status] = by_status.get(loop.status, 0) + 1
                by_domain[loop.domain] = by_domain.get(loop.domain, 0) + 1
            waiting = by_status.get("waiting", 0)
            if locked:
                bits = []
                for dom in ("career", "life", "both"):
                    n = sum(
                        1 for x in loops if x.domain == dom and x.status != "done"
                    )
                    if n:
                        bits.append(f"{n} {dom} loop{'s' if n != 1 else ''}")
                summary = ", ".join(bits) if bits else "no open loops"
                if waiting:
                    summary += f"; {waiting} waiting"
                return {
                    "locked": True,
                    "open": sum(1 for x in loops if x.status != "done"),
                    "by_status": by_status,
                    "spoken": summary,
                }
            return {
                "locked": False,
                "total": len(loops),
                "open": sum(1 for x in loops if x.status != "done"),
                "by_status": by_status,
                "by_domain": by_domain,
                "loops": [
                    {
                        "id": x.id,
                        "title": x.title,
                        "domain": x.domain,
                        "status": x.status,
                        "next_action": x.next_action,
                        "waiting_until": x.waiting_until,
                    }
                    for x in loops
                ],
            }

    # -- command bus --

    def apply(self, cmd: LoopCommand) -> dict:
        """Apply one command idempotently and persist. Returns a result dict.

        Replaying a previously seen ``idempotency_key`` returns the original
        result annotated with ``idempotent: True`` and mutates nothing.
        """
        with self._lock:
            prior = self._idem.get(cmd.idempotency_key)
            if prior is not None:
                result = dict(prior)
                result["idempotent"] = True
                return result

            result = self._dispatch(cmd)

            # Only record idempotency for effects that actually happened, so a
            # safe refusal (e.g. externalize without token) can be retried once
            # the caller supplies a valid review token.
            if result.get("_record_idem", True):
                stored = {k: v for k, v in result.items() if not k.startswith("_")}
                self._idem[cmd.idempotency_key] = stored
            result = {k: v for k, v in result.items() if not k.startswith("_")}
            result.setdefault("idempotent", False)
            self._save()
            return result

    def _dispatch(self, cmd: LoopCommand) -> dict:
        handler = getattr(self, f"_cmd_{cmd.type}", None)
        if handler is None:  # pragma: no cover - guarded by COMMAND_TYPES
            raise CommandError(f"unhandled command type: {cmd.type}")
        return handler(cmd.payload, cmd.source)

    # -- helpers --

    def _require_loop(self, payload: dict) -> Loop:
        loop_id = payload.get("loop_id")
        loop = self._loops.get(loop_id) if loop_id else None
        if not loop:
            raise CommandError(f"loop not found: {loop_id!r}")
        return loop

    def _touch(self, loop: Loop, event: str, source: str, **extra: Any) -> None:
        loop.updated_at = _now()
        entry = {"ts": loop.updated_at, "event": event, "source": source}
        entry.update(extra)
        loop.log.append(entry)

    # -- command handlers (each has an in-app twin, plan.md §4) --

    def _cmd_new_loop(self, payload: dict, source: str) -> dict:
        title = (payload.get("title") or "").strip()
        if not title:
            raise CommandError("title is required")
        domain = payload.get("domain", "career")
        if domain not in DOMAINS:
            raise CommandError(f"domain must be one of {sorted(DOMAINS)}")
        loop = Loop(
            id=_new_id("loop"),
            title=title[:200],
            domain=domain,
            why_it_matters=(payload.get("why_it_matters") or "").strip(),
            next_action=(payload.get("next_action") or "").strip(),
        )
        self._touch(loop, "created", source, title=loop.title, domain=domain)
        text = (payload.get("text") or "").strip()
        if text:
            loop.evidence.append(
                {
                    "id": _new_id("ev"),
                    "kind": "note",
                    "text": text,
                    "ts": _now(),
                    "source": source,
                }
            )
        self._loops[loop.id] = loop
        return {"ok": True, "loop_id": loop.id, "status": loop.status}

    def _cmd_update_loop(self, payload: dict, source: str) -> dict:
        loop = self._require_loop(payload)
        for field_name in ("why_it_matters", "next_action", "waiting_until"):
            if field_name in payload:
                setattr(loop, field_name, payload[field_name])
        link = payload.get("link")
        if link:
            loop.links.append({"id": _new_id("ln"), "url": link, "ts": _now()})
        step = payload.get("step")
        if step:
            loop.steps.append({"id": _new_id("st"), "text": step, "done": False})
        self._touch(loop, "updated", source)
        return {"ok": True, "loop_id": loop.id}

    def _cmd_log_evidence(self, payload: dict, source: str) -> dict:
        loop = self._require_loop(payload)
        kind = payload.get("kind", "note")
        item = {"id": _new_id("ev"), "kind": kind, "ts": _now(), "source": source}
        for key in ("text", "url", "pointer"):
            if payload.get(key):
                item[key] = payload[key]
        if not any(k in item for k in ("text", "url", "pointer")):
            raise CommandError("evidence needs one of: text, url, pointer")
        loop.evidence.append(item)
        self._touch(loop, "evidence_logged", source, evidence_id=item["id"])
        return {"ok": True, "loop_id": loop.id, "evidence_id": item["id"]}

    def _cmd_add_draft(self, payload: dict, source: str) -> dict:
        """Attach a draft. Safe: a draft is never externalized on creation."""
        loop = self._require_loop(payload)
        kind = payload.get("kind", "note")
        content = payload.get("content") or ""
        draft = {
            "id": _new_id("dr"),
            "kind": kind,
            "content": content,
            "externalized": False,
            "ts": _now(),
        }
        loop.drafts.append(draft)
        self._touch(loop, "draft_added", source, draft_id=draft["id"], kind=kind)
        return {"ok": True, "loop_id": loop.id, "draft_id": draft["id"]}

    def _cmd_delete_draft(self, payload: dict, source: str) -> dict:
        """Remove a single draft by id. Local and safe: deleting the local
        draft record never externalizes and never un-sends an already-sent
        draft — it only forgets the draft in SignalLoop. Idempotent-friendly:
        a repeat/double-tap for an already-gone draft returns ``removed: 0``
        rather than erroring.
        """
        loop = self._require_loop(payload)
        draft_id = payload.get("draft_id")
        if not draft_id:
            raise CommandError("draft_id is required for delete_draft")
        before = len(loop.drafts)
        loop.drafts = [d for d in loop.drafts if d.get("id") != draft_id]
        removed = before - len(loop.drafts)
        if removed:
            self._touch(loop, "draft_deleted", source, draft_id=draft_id)
        return {"ok": True, "loop_id": loop.id, "draft_id": draft_id, "removed": removed}

    def _cmd_pause(self, payload: dict, source: str) -> dict:
        loop = self._require_loop(payload)
        loop.status = "paused"
        self._touch(loop, "paused", source)
        return {"ok": True, "loop_id": loop.id, "status": loop.status}

    def _cmd_resume(self, payload: dict, source: str) -> dict:
        loop = self._require_loop(payload)
        loop.status = "active"
        self._touch(loop, "resumed", source)
        return {"ok": True, "loop_id": loop.id, "status": loop.status}

    def _cmd_approve_plan(self, payload: dict, source: str) -> dict:
        """Approve an internal, reversible plan — never an externalization."""
        loop = self._require_loop(payload)
        loop.plan_approved = True
        self._touch(loop, "plan_approved", source)
        return {"ok": True, "loop_id": loop.id, "plan_approved": True}

    def _cmd_mark_complete(self, payload: dict, source: str) -> dict:
        loop = self._require_loop(payload)
        loop.status = "done"
        loop.outcome = payload.get("outcome") or loop.outcome or "completed"
        self._touch(loop, "completed", source, outcome=loop.outcome)
        return {"ok": True, "loop_id": loop.id, "status": "done", "outcome": loop.outcome}

    def _cmd_request_review(self, payload: dict, source: str) -> dict:
        """Open an authenticated-review request for a consequential action."""
        loop = self._require_loop(payload)
        action = (payload.get("action") or "").strip()
        if not action:
            raise CommandError("action is required for request_review")
        review = Review(
            id=_new_id("rv"),
            loop_id=loop.id,
            action=action,
            draft_id=payload.get("draft_id"),
        )
        self._reviews[review.id] = review
        self._touch(loop, "review_requested", source, review_id=review.id, action=action)
        return {"ok": True, "review_id": review.id, "status": "pending"}

    def _cmd_resolve_review(self, payload: dict, source: str) -> dict:
        """Approve/reject a review. Approval mints a single-use review token.

        In the product this only happens in an authenticated foreground review;
        the server stands in for that gate today. A general voice "approve" must
        never reach this path (AGENTS.md safety).
        """
        review = self._reviews.get(payload.get("review_id"))
        if not review:
            raise CommandError(f"review not found: {payload.get('review_id')!r}")
        if review.status != "pending":
            return {
                "ok": True,
                "review_id": review.id,
                "status": review.status,
                "note": "already resolved",
            }
        approved = bool(payload.get("approved"))
        review.resolved_at = _now()
        if approved:
            review.status = "approved"
            review.token = _new_id("tok")
        else:
            review.status = "rejected"
        loop = self._loops.get(review.loop_id)
        if loop:
            self._touch(loop, "review_resolved", source, review_id=review.id,
                        status=review.status)
        out = {"ok": True, "review_id": review.id, "status": review.status}
        if review.token:
            out["review_token"] = review.token
        return out

    def _cmd_externalize(self, payload: dict, source: str) -> dict:
        """Send/post/commit a draft — requires a valid approved review token.

        This is the one place a consequential side effect can happen, and it is
        gated. Without a valid, unused token we refuse safely and do NOT record
        idempotency, so the caller can retry after a real review.
        """
        loop = self._require_loop(payload)
        draft_id = payload.get("draft_id")
        draft = next((d for d in loop.drafts if d["id"] == draft_id), None)
        if not draft:
            raise CommandError(f"draft not found on loop: {draft_id!r}")

        token = payload.get("review_token")
        review = next(
            (
                r
                for r in self._reviews.values()
                if r.token
                and r.token == token
                and r.status == "approved"
                and not r.consumed
                and r.loop_id == loop.id
            ),
            None,
        )
        if not review:
            # Safe refusal — never a silent externalize.
            self._touch(loop, "externalize_refused", source, draft_id=draft_id,
                        reason="review_required")
            return {
                "ok": False,
                "externalized": False,
                "reason": "review_required",
                "loop_id": loop.id,
                "draft_id": draft_id,
                "_record_idem": False,
            }

        review.consumed = True
        draft["externalized"] = True
        draft["externalized_at"] = _now()
        self._touch(loop, "externalized", source, draft_id=draft_id,
                    review_id=review.id)
        return {
            "ok": True,
            "externalized": True,
            "loop_id": loop.id,
            "draft_id": draft_id,
            "review_id": review.id,
        }

    def _cmd_remember(self, payload: dict, source: str) -> dict:
        """Append a durable global fact/preference (not Siri memory)."""
        text = (payload.get("text") or "").strip()
        if not text:
            raise CommandError("text is required for remember")
        fact = {"id": _new_id("fact"), "text": text, "ts": _now(), "source": source}
        self._facts.append(fact)
        return {"ok": True, "fact_id": fact["id"]}

    def _cmd_clear_suggestions(self, payload: dict, source: str) -> dict:
        """Remove a loop's AI suggestion drafts and reset its suggested action.

        Deletes every ``kind == "suggestion"`` draft, blanks the AI-set
        ``next_action`` headline, and forgets today's suggest idempotency so the
        next Suggest tap regenerates a fresh action instead of returning a
        now-deleted draft. Purely local and safe — it externalizes nothing and
        the user can regenerate at will.
        """
        loop = self._require_loop(payload)
        before = len(loop.drafts)
        loop.drafts = [d for d in loop.drafts if d.get("kind") != "suggestion"]
        removed = before - len(loop.drafts)
        loop.next_action = ""
        prefixes = (f"suggest-next:{loop.id}:", f"suggest-draft:{loop.id}:")
        for key in [k for k in self._idem if k.startswith(prefixes)]:
            del self._idem[key]
        self._touch(loop, "suggestions_cleared", source, removed=removed)
        return {"ok": True, "loop_id": loop.id, "removed": removed}


# Process-wide singleton, mirroring server.store.store.
engine = LoopEngine()
