# SignalLoop engagement scout: per-wake discovery of who to connect/comment with.
"""Engagement scout — the per-wake unit that finds the right people/posts and
drafts connect/comment actions for review.

This is a *server-layer* capability (the reusable unit a daily cloud-wake job
calls), never part of the core LoopEngine. For one loop it:

  1. reads the loop's context and derives a topic query,
  2. asks a **connector** (default: the offline :class:`~server.connectors.StubConnector`)
     for candidate people and posts,
  3. scores each candidate against the loop's target/proof using deterministic
     keyword overlap — **no model call**, so the whole unit runs without an API
     key,
  4. writes reviewable ``connect`` / ``comment`` drafts back through the
     LoopCommandBus (``add_draft``), idempotent per candidate-per-day.

Nothing here externalizes: a connect note or a comment is a **draft you
review**. Per AGENTS.md a background/cloud job "may research, fetch, draft, or
notify" but may never silently externalize — actually connecting or commenting
stays gated behind ``externalize`` + an authenticated-review token. Because each
candidate maps to a deterministic idempotency key, re-running a day never
duplicates a draft, and repeated cloud wakes accumulate only genuinely new
candidates.
"""

from __future__ import annotations

import re
import time
from datetime import date

from .connectors import Candidate, Connector, get_connector
from .loops import LoopCommand, engine

# Kinds of engagement drafts this unit produces. Both are *externalizations*
# once reviewed (connecting / commenting), so both stay behind the review gate.
KINDS = ("connect", "comment")

_WORD = re.compile(r"[a-z0-9]+")

# Small stopword set (includes common 2-letter words so tokens like "ai" and
# "ml" survive while "of"/"to" do not).
_STOP = {
    "the", "and", "for", "with", "that", "this", "you", "your", "our", "are",
    "was", "into", "from", "out", "who", "how", "why", "what", "when", "will",
    "can", "get", "got", "has", "have", "had", "not", "but", "all", "any",
    "of", "to", "in", "on", "is", "it", "as", "at", "an", "or", "be", "by",
    "we", "us", "my", "me", "so", "up", "do", "if", "no",
}


def _norm(word: str) -> str:
    """Lowercase token with a crude singularization so ``agents`` matches
    ``agent`` and ``systems`` matches ``system`` (keeps ``business`` intact)."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _tokens(text: str) -> set[str]:
    """Content tokens of ``text``: lowercased, singularized, stopwords removed."""
    out: set[str] = set()
    for raw in _WORD.findall((text or "").lower()):
        if len(raw) < 2 or raw in _STOP:
            continue
        out.add(_norm(raw))
    return out


def _loop_keywords(loop: dict) -> set[str]:
    """Derive the loop's topic vocabulary from its most descriptive fields."""
    parts = [
        loop.get("title", ""),
        loop.get("why_it_matters", ""),
        loop.get("next_action", ""),
    ]
    parts += [s.get("text", "") for s in loop.get("steps", [])]
    parts += [
        (ev.get("text") or "") for ev in loop.get("evidence", [])[-6:]
    ]
    kw: set[str] = set()
    for p in parts:
        kw |= _tokens(p)
    return kw


def _candidate_tokens(c: Candidate) -> set[str]:
    toks: set[str] = set()
    for t in c.topics:
        toks |= _tokens(t)
    toks |= _tokens(c.text)
    return toks


def _score(c: Candidate, kw: set[str]) -> tuple[int, list[str]]:
    """Return (overlap count, sorted matched terms) of a candidate vs the loop."""
    matched = sorted(kw & _candidate_tokens(c))
    return len(matched), matched


def _platform_label(c: Candidate) -> str:
    return {"x": "X", "linkedin": "LinkedIn"}.get(c.platform, c.platform or "social")


def _first_name(name: str) -> str:
    return (name.split() or ["there"])[0]


def _connect_content(c: Candidate, loop: dict, matched: list[str]) -> str:
    """A reviewable connect-note draft. References only real, matched topics and
    the loop title — never fabricated claims about the user."""
    title = loop.get("title") or "what I'm building"
    topics = ", ".join(matched[:3]) or "shared interests"
    lines = [
        f"[connect \u00b7 {_platform_label(c)}] {c.name} ({c.handle})",
        f"Why now: overlaps with {topics}.",
        f"About them: {c.text}",
    ]
    if c.url:
        lines.append(f"Profile: {c.url}")
    lines += [
        "",
        "Draft note (review before sending):",
        f"\u201cHi {_first_name(c.name)} \u2014 I'm working on {title}. Your work on "
        f"{topics} lines up with what I'm building; would love to connect and "
        f"compare notes.\u201d",
    ]
    return "\n".join(lines)


def _comment_content(c: Candidate, loop: dict, matched: list[str]) -> str:
    """A reviewable comment draft on a candidate post."""
    title = loop.get("title") or "what I'm building"
    topics = ", ".join(matched[:3]) or "this"
    focus = matched[0] if matched else "this"
    lines = [
        f"[comment \u00b7 {_platform_label(c)}] on {c.handle}'s post",
        f"Post: \u201c{c.text}\u201d",
        f"Why engage: overlaps with {topics}.",
    ]
    if c.url:
        lines.append(f"Link: {c.url}")
    lines += [
        "",
        "Draft reply (review before posting):",
        f"\u201cThis resonates \u2014 I'm building {title}. How are you thinking "
        f"about {focus}?\u201d",
    ]
    return "\n".join(lines)


def scout_for_loop(
    loop: dict,
    *,
    source: str = "cloud_wake",
    today: str | None = None,
    force: bool = False,
    platform: str | None = None,
    limit: int = 3,
    connector: Connector | None = None,
) -> dict:
    """Find engagement candidates for one loop and persist reviewable drafts.

    Scores every candidate the connector returns against the loop's keywords,
    keeps the top ``limit`` people (→ ``connect`` drafts) and top ``limit``
    posts (→ ``comment`` drafts), and writes each via the command bus with a
    deterministic per-candidate-per-day idempotency key. Re-running the same day
    is a no-op (``new: 0``, ``cached: True``); ``force`` writes fresh drafts.
    Nothing is externalized.
    """
    today = today or date.today().isoformat()
    lid = loop["id"]
    conn = connector or get_connector()
    kw = _loop_keywords(loop)

    query = " ".join(
        x for x in (loop.get("title", ""), loop.get("why_it_matters", "")) if x
    )
    candidates = conn.find_candidates(query, platform=platform, limit=max(limit * 3, 6))

    scored: list[tuple[int, Candidate, list[str]]] = []
    for c in candidates:
        n, matched = _score(c, kw)
        if n > 0:
            scored.append((n, c, matched))
    # Deterministic: strongest match first, then stable by candidate id.
    scored.sort(key=lambda t: (-t[0], t[1].id))

    people = [(c, m) for _n, c, m in scored if c.kind == "person"][:limit]
    posts = [(c, m) for _n, c, m in scored if c.kind == "post"][:limit]

    results: list[dict] = []

    def _emit(c: Candidate, matched: list[str], kind: str, content: str) -> None:
        key = f"scout-{kind}:{lid}:{c.id}:{today}"
        if force:
            key += f":{int(time.time() * 1000)}"
        res = engine.apply(
            LoopCommand.from_dict(
                {
                    "type": "add_draft",
                    "payload": {"loop_id": lid, "kind": kind, "content": content},
                    "source": source,
                    "idempotency_key": key,
                }
            )
        )
        results.append(
            {
                "candidate_id": c.id,
                "name": c.name,
                "handle": c.handle,
                "platform": c.platform,
                "kind": kind,
                "score": len(matched),
                "matched": matched,
                "draft_id": res.get("draft_id"),
                "idempotent": bool(res.get("idempotent")),
            }
        )

    for c, m in people:
        _emit(c, m, "connect", _connect_content(c, loop, m))
    for c, m in posts:
        _emit(c, m, "comment", _comment_content(c, loop, m))

    new = sum(1 for r in results if not r["idempotent"])
    return {
        "loop_id": lid,
        "title": loop.get("title"),
        "date": today,
        "connector": conn.name,
        "platform": platform,
        "candidates": len(results),
        "connect": sum(1 for r in results if r["kind"] == "connect"),
        "comment": sum(1 for r in results if r["kind"] == "comment"),
        "new": new,
        "cached": new == 0 and bool(results),
        "results": results,
    }


def scout_active(
    loop_id: str | None = None,
    *,
    source: str = "cloud_wake",
    force: bool = False,
    platform: str | None = None,
    limit: int = 3,
) -> dict:
    """Scout one loop (``loop_id``) or every active loop.

    Today this is triggered on demand via ``POST /v1/scout``; the same unit is
    what a daily cloud-wake job calls. ``force`` refreshes even if drafts for
    today already exist.
    """
    today = date.today().isoformat()
    if loop_id:
        loop = engine.get_loop(loop_id)
        if not loop:
            raise KeyError(loop_id)
        loops = [loop]
    else:
        loops = [l for l in engine.list_loops() if l.get("status") == "active"]

    scouted = [
        scout_for_loop(
            l, source=source, today=today, force=force, platform=platform, limit=limit
        )
        for l in loops
    ]
    return {"date": today, "count": len(scouted), "scouted": scouted}
