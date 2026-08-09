# SignalLoop action suggester: turn a loop into today's suggested next actions.
"""Loop action suggester — proposes today's next action(s) for a loop.

This is a *server-layer* capability (it may call the model), never part of the
core LoopEngine. It reads a loop's current context, asks the model for a small
set of concrete, safe next actions, and writes the result back through the
LoopCommandBus (``update_loop.next_action`` + an ``add_draft`` suggestion) so
the engine stays the single source of truth (AGENTS.md invariants).

Nothing here externalizes anything: a suggestion is a draft you review. The
*daily* cadence is a scheduling concern for the cloud wake plane; this module
is the reusable per-loop unit that a scheduler (or a manual trigger today)
calls. Writes are idempotent per loop-per-day, so re-running a day is a no-op
and a new day produces a fresh suggestion.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, time as dtime

from odysseus import provider

from .config import config
from .loops import LoopCommand, engine

SYSTEM = (
    "You are SignalLoop, a pragmatic career/life 'loop' coach. Given ONE open "
    "loop, propose the smallest set of concrete next actions the person can "
    "take TODAY to move it forward. Be specific and realistic. Work ONLY from "
    "the loop context provided; never invent facts about the person. You cannot "
    "browse the web or send anything — you only suggest actions the person will "
    "do or review themselves.\n\n"
    "Respond with STRICT JSON only — no prose, no markdown, no code fences:\n"
    '{"next_action": "<one short imperative sentence: the single most important '
    'thing to do next>", "actions": ["<action 1>", "<action 2>", "<action 3>"], '
    '"why": "<one sentence on why these advance the loop>"}\n'
    "Give 1-3 actions, each under ~140 characters."
)


def _loop_context(loop: dict) -> str:
    """Render a compact, model-friendly snapshot of the loop's current state."""
    lines = [
        f"Title: {loop.get('title', '')}",
        f"Domain: {loop.get('domain', 'career')}",
        f"Status: {loop.get('status', 'active')}",
    ]
    if loop.get("why_it_matters"):
        lines.append(f"Why it matters: {loop['why_it_matters']}")
    if loop.get("next_action"):
        lines.append(f"Current next action: {loop['next_action']}")
    if loop.get("waiting_until"):
        lines.append(f"Waiting until: {loop['waiting_until']}")

    steps = [s for s in loop.get("steps", []) if not s.get("done")]
    if steps:
        lines.append("Open steps:")
        lines += [f"- {s.get('text', '')}" for s in steps[:8]]

    evidence = loop.get("evidence", [])
    if evidence:
        lines.append("Evidence so far:")
        for ev in evidence[-8:]:
            piece = ev.get("text") or ev.get("url") or ev.get("pointer") or ""
            if piece:
                lines.append(f"- ({ev.get('kind', 'note')}) {piece}")

    log = loop.get("log", [])
    if log:
        recent = ", ".join(e.get("event", "") for e in log[-6:] if e.get("event"))
        if recent:
            lines.append(f"Recent activity: {recent}")

    return "\n".join(lines)


def _extract_json(text: str) -> dict:
    """Best-effort parse of a JSON object from a model reply.

    Tolerates code fences and leading/trailing prose by extracting the first
    balanced ``{...}`` span. Returns {} when nothing parseable is found so the
    caller can fall back to the raw text.
    """
    if not text:
        return {}
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        nl = cleaned.find("\n")
        if nl != -1:
            cleaned = cleaned[nl + 1 :]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError:
            return {}
    return {}


def suggest_for_loop(
    loop: dict,
    *,
    source: str = "cloud_wake",
    today: str | None = None,
    force: bool = False,
) -> dict:
    """Generate and persist today's suggested next action(s) for one loop.

    Writes back two idempotent (per loop-per-day) commands: ``update_loop`` to
    set the headline ``next_action``, and ``add_draft`` to attach the full
    reviewable suggestion. Returns a summary of what was suggested.

    If a suggestion was already produced for this loop today, the model call is
    skipped and the persisted suggestion is returned (``cached: True``) — so a
    daily-job retry is a true no-op. Pass ``force=True`` for an intentional
    refresh, which writes a fresh suggestion under a unique key.
    """
    today = today or date.today().isoformat()
    lid = loop["id"]
    next_key = f"suggest-next:{lid}:{today}"
    draft_key = f"suggest-draft:{lid}:{today}"

    if not force and engine.seen(draft_key):
        fresh = engine.get_loop(lid) or loop
        existing = next(
            (d for d in reversed(fresh.get("drafts", []))
             if d.get("kind") == "suggestion"),
            None,
        )
        return {
            "loop_id": lid,
            "title": fresh.get("title"),
            "next_action": fresh.get("next_action", ""),
            "actions": [],
            "why": "",
            "draft_id": existing["id"] if existing else None,
            "date": today,
            "cached": True,
        }

    if force:
        suffix = f":{int(time.time())}"
        next_key += suffix
        draft_key += suffix

    model = config.model or provider.DEFAULT_MODEL
    out = provider.complete(
        model, SYSTEM, [{"role": "user", "text": _loop_context(loop)}], []
    )
    raw = (out.get("text") or "").strip()
    parsed = _extract_json(raw)

    next_action = (parsed.get("next_action") or "").strip()
    actions = [a.strip() for a in (parsed.get("actions") or []) if str(a).strip()]
    why = (parsed.get("why") or "").strip()
    if not next_action and actions:
        next_action = actions[0]

    if next_action:
        engine.apply(
            LoopCommand.from_dict(
                {
                    "type": "update_loop",
                    "payload": {"loop_id": lid, "next_action": next_action},
                    "source": source,
                    "idempotency_key": next_key,
                }
            )
        )

    body_lines: list[str] = []
    if actions:
        body_lines.append("Suggested actions for today:")
        body_lines += [f"- {a}" for a in actions]
    elif raw:
        body_lines.append(raw)
    if why:
        body_lines += ["", f"Why: {why}"]
    content = "\n".join(body_lines).strip() or next_action or raw

    draft_res = engine.apply(
        LoopCommand.from_dict(
            {
                "type": "add_draft",
                "payload": {"loop_id": lid, "kind": "suggestion", "content": content},
                "source": source,
                "idempotency_key": draft_key,
            }
        )
    )

    return {
        "loop_id": lid,
        "title": loop.get("title"),
        "next_action": next_action,
        "actions": actions,
        "why": why,
        "draft_id": draft_res.get("draft_id"),
        "date": today,
        "cached": False,
        "usage": out.get("usage"),
    }


def suggest_active(
    loop_id: str | None = None, *, source: str = "cloud_wake", force: bool = False
) -> dict:
    """Suggest for one loop (``loop_id``) or every active loop.

    This is the unit a daily cloud-wake job will call; today it is triggered
    on demand via ``POST /v1/suggest``. ``force`` refreshes even if a
    suggestion already exists for today.
    """
    today = date.today().isoformat()
    if loop_id:
        loop = engine.get_loop(loop_id)
        if not loop:
            raise KeyError(loop_id)
        loops = [loop]
    else:
        loops = [l for l in engine.list_loops() if l.get("status") == "active"]

    suggested = [
        suggest_for_loop(l, source=source, today=today, force=force) for l in loops
    ]
    return {"date": today, "count": len(suggested), "suggested": suggested}
