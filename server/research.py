# SignalLoop deep research: web-grounded key insights for a loop.
"""Loop deep-research — web-grounded key insights for one loop.

This is a *server-layer* capability (it calls the model with OpenAI web search),
never part of the core LoopEngine. It reads a loop's context, asks the model to
research the topic online, and writes the result back through the LoopCommandBus
as a reviewable ``research`` draft (``add_draft``) so the engine stays the single
source of truth (AGENTS.md invariants).

Nothing here externalizes anything: a research report is a draft you review. Per
AGENTS.md, a background/cloud job "may research, fetch, draft, or notify" but may
never silently externalize — deep research is exactly that allowed shape. Writes
are idempotent per loop-per-day, so re-running a day is a no-op and ``force``
produces a fresh report. Web search is best-effort: if the Responses API/web
tool is unavailable, we fall back to a model-only analysis so the feature still
returns key insights.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import date

from odysseus import provider

from .config import config
from .loops import LoopCommand, engine
from .suggester import _loop_context

# Deep-research instructions. Unlike the suggester (which cannot browse), this
# capability is explicitly allowed to use web search and MUST ground its key
# insights in what it finds — while never inventing facts about the person and
# never taking any external action.
INSTRUCTIONS = (
    "You are SignalLoop Deep Research. Research the user's loop topic using web "
    "search and surface the most useful, CURRENT key insights to help them "
    "advance it. Prefer recent, credible sources and concrete facts/numbers. "
    "Do NOT invent facts about the person; work from the loop context plus what "
    "you find online. You cannot send, post, spend, or take any external "
    "action — you only research and report for the person to review.\n\n"
    "Write a concise, skimmable report in PLAIN TEXT (no markdown headers, no "
    "code fences). Use these exact section labels, each on its own line, "
    "followed by bullet lines that start with '- ':\n"
    "Key insights:\n"
    "- <the essential fact/number and why it matters> (give 3-6)\n"
    "Implications for your loop:\n"
    "- <how this should change the plan or what to prioritize> (give 1-3)\n"
    "Suggested next actions:\n"
    "- <one concrete action the person can take next> (give 1-3)\n"
    "Keep each bullet under ~200 characters. No preamble, no closing remarks."
)

# How long to wait on the (potentially multi-step) web-search call.
_RESEARCH_TIMEOUT_S = 180


def _responses_web_search(query: str, model: str) -> dict:
    """Call the OpenAI Responses API with the web_search tool.

    Returns ``{"text": str, "sources": [{"title","url"}], "usage": {...}}``.
    Raises RuntimeError on a permanent failure so the caller can fall back to a
    model-only analysis. Tries the current ``web_search`` tool name first and
    falls back to the older ``web_search_preview`` alias.
    """
    url = f"{provider.API_BASE}/responses"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {provider.api_key()}",
    }

    def _once(tool_type: str) -> dict:
        body = {
            "model": model,
            "instructions": INSTRUCTIONS,
            "input": query,
            "tools": [{"type": tool_type}],
            "tool_choice": "auto",
            "max_output_tokens": 1200,
        }
        payload = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=_RESEARCH_TIMEOUT_S) as resp:
            return json.loads(resp.read().decode("utf-8"))

    data = None
    last_err: Exception | None = None
    for tool_type in ("web_search", "web_search_preview"):
        for attempt in range(3):
            try:
                data = _once(tool_type)
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode("utf-8", "replace")[:400]
                # A bad tool type is permanent for this alias — try the next
                # alias rather than burning retries on it.
                if e.code == 400 and "tool" in detail.lower():
                    last_err = RuntimeError(f"HTTP 400: {detail}")
                    break
                if e.code in (429, 500, 502, 503) and attempt < 2:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise RuntimeError(f"HTTP {e.code}: {detail}")
            except (urllib.error.URLError, TimeoutError) as e:
                last_err = e
                if attempt < 2:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise RuntimeError(f"web search request failed: {e}")
        if data is not None:
            break
    if data is None:
        raise RuntimeError(f"web search unavailable: {last_err}")

    texts: list[str] = []
    sources: list[dict] = []
    seen: set[str] = set()
    for item in data.get("output", []) or []:
        if item.get("type") != "message":
            continue
        for chunk in item.get("content", []) or []:
            if chunk.get("type") != "output_text":
                continue
            texts.append(chunk.get("text", ""))
            for ann in chunk.get("annotations", []) or []:
                if ann.get("type") == "url_citation":
                    u = ann.get("url")
                    if u and u not in seen:
                        seen.add(u)
                        sources.append({"title": ann.get("title") or u, "url": u})

    usage = data.get("usage", {}) or {}
    return {
        "text": "\n".join(t for t in texts if t).strip(),
        "sources": sources,
        "usage": {
            "input": usage.get("input_tokens", 0),
            "output": usage.get("output_tokens", 0),
        },
    }


def _compose_content(report: str, sources: list[dict]) -> str:
    """Assemble the reviewable draft body: the report plus a Sources list."""
    body = report.strip()
    if sources:
        lines = [body, "", "Sources:"]
        for s in sources[:8]:
            lines.append(f"- {s['url']}")
        body = "\n".join(lines).strip()
    return body


def _clear_prior_research(loop_id: str, source: str) -> None:
    """Delete any existing ``research`` drafts so only the newest remains.

    Keeps the loop tidy (one live research report) and makes the phone's
    "latest research" the single source of truth. Local and safe.
    """
    fresh = engine.get_loop(loop_id)
    if not fresh:
        return
    for d in list(fresh.get("drafts", [])):
        if d.get("kind") == "research":
            engine.apply(
                LoopCommand.from_dict(
                    {
                        "type": "delete_draft",
                        "payload": {"loop_id": loop_id, "draft_id": d["id"]},
                        "source": source,
                        "idempotency_key": f"research-clear:{loop_id}:{d['id']}",
                    }
                )
            )


def research_for_loop(
    loop: dict,
    *,
    source: str = "cloud_wake",
    today: str | None = None,
    force: bool = False,
) -> dict:
    """Run web-grounded deep research for one loop and persist a ``research``
    draft with the key insights.

    Idempotent per loop-per-day: if a research report already exists for today
    the model/web call is skipped and the persisted report is returned
    (``cached: True``). ``force`` writes a fresh report under a unique key. Web
    search is best-effort; on failure we fall back to a model-only analysis and
    set ``web_used: False``.
    """
    today = today or date.today().isoformat()
    lid = loop["id"]
    draft_key = f"research-draft:{lid}:{today}"

    if not force and engine.seen(draft_key):
        fresh = engine.get_loop(lid) or loop
        existing = next(
            (d for d in reversed(fresh.get("drafts", []))
             if d.get("kind") == "research"),
            None,
        )
        if existing is not None:
            return {
                "loop_id": lid,
                "title": fresh.get("title"),
                "draft_id": existing["id"],
                "date": today,
                "cached": True,
                "web_used": None,
                "sources": 0,
            }

    if force:
        draft_key += f":{int(time.time())}"

    model = config.model or provider.DEFAULT_MODEL
    query = "Research this loop and report key insights:\n\n" + _loop_context(loop)

    web_used = True
    sources: list[dict] = []
    usage: dict | None = None
    try:
        result = _responses_web_search(query, model)
        report = result["text"]
        sources = result["sources"]
        usage = result["usage"]
        if not report:
            raise RuntimeError("empty research result")
    except Exception:
        # Graceful fallback: model-only analysis (no live web) still yields
        # useful key insights so the feature never hard-fails on the phone.
        web_used = False
        out = provider.complete(
            model, INSTRUCTIONS, [{"role": "user", "text": query}], []
        )
        report = (out.get("text") or "").strip()
        usage = out.get("usage")

    content = _compose_content(report, sources)
    if not content:
        content = "No research results were available. Try again shortly."

    _clear_prior_research(lid, source)
    draft_res = engine.apply(
        LoopCommand.from_dict(
            {
                "type": "add_draft",
                "payload": {"loop_id": lid, "kind": "research", "content": content},
                "source": source,
                "idempotency_key": draft_key,
            }
        )
    )

    return {
        "loop_id": lid,
        "title": loop.get("title"),
        "draft_id": draft_res.get("draft_id"),
        "date": today,
        "cached": False,
        "web_used": web_used,
        "sources": len(sources),
        "usage": usage,
    }


def research_active(
    loop_id: str | None = None, *, source: str = "cloud_wake", force: bool = False
) -> dict:
    """Deep-research one loop (``loop_id``) or every active loop.

    Today this is triggered on demand via ``POST /v1/research``; a future
    cloud-wake job can call the same unit. ``force`` refreshes even if a report
    already exists for today.
    """
    today = date.today().isoformat()
    if loop_id:
        loop = engine.get_loop(loop_id)
        if not loop:
            raise KeyError(loop_id)
        loops = [loop]
    else:
        loops = [l for l in engine.list_loops() if l.get("status") == "active"]

    researched = [
        research_for_loop(l, source=source, today=today, force=force) for l in loops
    ]
    return {"date": today, "count": len(researched), "researched": researched}
