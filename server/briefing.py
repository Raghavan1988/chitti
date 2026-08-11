# SignalLoop Daily Briefing: audio digest + editable X post + person-to-know.
"""Daily Briefing generator (PRD §4).

For one loop, this produces the three-part morning briefing:

  1. an **audio digest** — a short, listenable podcast recap (transcript +
     TTS audio + cited sources),
  2. one **editable X/Twitter post** that shares a useful insight in the
     user's voice, and
  3. a **person to know** — a relevant public LinkedIn/X profile with public
     context and genuine ways to engage.

It is a *server-layer* capability (and the unit the daily cloud-wake scheduler
calls), never part of the core LoopEngine. Grounding comes from the existing
deep-research pass (``research.py``), which uses live web search with citations.

Guardrails (PRD "Trust and Guardrails"):
  * Nothing here externalizes. The post is a DRAFT the user reviews and posts
    from the foreground; SignalLoop never auto-posts or auto-messages.
  * People discovery uses only public professional info, never infers sensitive
    attributes, and frames engagement as genuine (not spam). Profile URLs are
    left blank when not confident rather than fabricated.
  * Source-grounded claims (digest) are kept distinct from discovered
    public-profile info (person), and sources are cited where available.

Writes are idempotent per loop-per-day; ``force`` regenerates. Audio is
synthesized lazily (on first listen) and cached.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date

from odysseus import provider

from . import research
from .config import config
from .loops import LoopCommand, engine
from .suggester import _extract_json, _loop_context

SYSTEM = (
    "You are SignalLoop, producing a person's DAILY BRIEFING for one topic loop. "
    "You are given the loop context and today's web-researched key insights. "
    "Produce three things that help them learn, build their voice, and grow their "
    "network on this topic.\n\n"
    "Rules:\n"
    "- Ground the digest and post in the provided insights; do NOT invent facts "
    "about the person.\n"
    "- People discovery: suggest ONE genuinely relevant, notable PUBLIC figure in "
    "this field — a REAL, publicly-known person who is NOT the user (e.g. a "
    "well-known researcher, founder, or practitioner the user could learn from and "
    "thoughtfully engage with). Never return the user, a placeholder, or an "
    "invented name. Use only public professional information. Never infer sensitive "
    "attributes. Do NOT fabricate a profile URL — leave profile_url empty if you "
    "are not confident it is correct. Frame engagement as authentic interaction, "
    "never spam or automation.\n"
    "- The post is a draft the person will review before publishing; keep it in a "
    "natural, credible first-person voice.\n\n"
    "Respond with STRICT JSON only — no prose, no markdown, no code fences:\n"
    "{\n"
    '  "digest": {"transcript": "<90-160 word first-person spoken recap of what\'s '
    'notable today and one meaningful thing to do>", "key_points": ["<short '
    'point>", "..."]},\n'
    '  "post": {"text": "<<=270 char X/Twitter post sharing one useful insight in '
    'the user\'s voice; at most 2 tasteful hashtags>"},\n'
    '  "person": {"name": "<full name of a REAL, publicly-known person in this '
    'field who is NOT the user>", "platform": "linkedin|x", "profile_url": '
    '"<canonical public URL or empty>", "context": "<1-2 sentences of public '
    'professional context>", "why_relevant": "<why they matter to THIS loop>", '
    '"engagement_tips": ["<one genuine way to engage>", "..."]}\n'
    "}\n"
    "Give 2-4 key_points and 1-3 engagement_tips."
)

_TTS_MODEL = "gpt-4o-mini-tts"
_TTS_VOICE = "alloy"
_lock = threading.RLock()
_URL_RE = re.compile(r"https?://[^\s)]+")


# -- storage -----------------------------------------------------------------

def _briefing_dir() -> str:
    d = os.path.join(str(config.workdir), ".chitti", "briefings")
    os.makedirs(d, exist_ok=True)
    return d


def _audio_dir() -> str:
    d = os.path.join(str(config.workdir), ".chitti", "audio")
    os.makedirs(d, exist_ok=True)
    return d


def _path(loop_id: str) -> str:
    return os.path.join(_briefing_dir(), f"{loop_id}.json")


def _read(loop_id: str) -> dict | None:
    p = _path(loop_id)
    if not os.path.isfile(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return None


def _write(loop_id: str, data: dict) -> None:
    tmp = _path(loop_id) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _path(loop_id))


# -- grounding ---------------------------------------------------------------

def _insights_and_sources(loop: dict, today: str, force: bool) -> tuple[str, list[str]]:
    """Ensure today's deep-research exists and return (insights_text, sources).

    Reuses ``research.research_for_loop`` (per-day cached) so the briefing is
    grounded in the same web-researched insights the user can inspect, then
    reads the freshest ``research`` draft back off the loop.
    """
    try:
        research.research_for_loop(loop, source="cloud_wake", today=today, force=force)
    except Exception:
        pass  # Research is best-effort; the briefing can still run on loop context.

    fresh = engine.get_loop(loop["id"]) or loop
    draft = next(
        (d for d in reversed(fresh.get("drafts", [])) if d.get("kind") == "research"),
        None,
    )
    text = (draft or {}).get("content", "") if draft else ""
    sources = _URL_RE.findall(text) if text else []
    # De-dupe, keep order.
    seen: set[str] = set()
    sources = [u for u in sources if not (u in seen or seen.add(u))]
    return text, sources


# -- generation --------------------------------------------------------------

def generate_for_loop(
    loop: dict,
    *,
    source: str = "cloud_wake",
    today: str | None = None,
    force: bool = False,
) -> dict:
    """Generate and persist today's Daily Briefing for one loop.

    Idempotent per loop-per-day: if a briefing already exists for today the
    model calls are skipped and the stored briefing is returned (``cached``).
    ``force`` regenerates a fresh briefing (and clears cached audio).
    """
    today = today or date.today().isoformat()
    lid = loop["id"]

    with _lock:
        existing = _read(lid)
        if existing and existing.get("date") == today and not force:
            existing["cached"] = True
            existing["has_audio"] = _has_audio(lid, today)
            return existing

    insights, sources = _insights_and_sources(loop, today, force)

    context = _loop_context(loop)
    if insights:
        context += "\n\nToday's researched key insights:\n" + insights

    model = config.model or provider.DEFAULT_MODEL
    out = provider.complete(model, SYSTEM, [{"role": "user", "text": context}], [])
    parsed = _extract_json(out.get("text") or "")

    digest = parsed.get("digest") or {}
    post = parsed.get("post") or {}
    person = parsed.get("person") or {}

    transcript = (digest.get("transcript") or "").strip()
    key_points = [str(p).strip() for p in (digest.get("key_points") or []) if str(p).strip()]
    post_text = (post.get("text") or "").strip()
    person = {
        "name": (person.get("name") or "").strip(),
        "platform": (person.get("platform") or "").strip().lower(),
        "profile_url": (person.get("profile_url") or "").strip(),
        "context": (person.get("context") or "").strip(),
        "why_relevant": (person.get("why_relevant") or "").strip(),
        "engagement_tips": [
            str(t).strip() for t in (person.get("engagement_tips") or []) if str(t).strip()
        ],
    }

    briefing = {
        "loop_id": lid,
        "title": loop.get("title"),
        "date": today,
        "digest": {"transcript": transcript, "key_points": key_points},
        "post": {"text": post_text},
        "person": person,
        "sources": sources,
        "feedback": {},
        "dismissed": {},
        "cached": False,
    }

    with _lock:
        _clear_audio(lid)  # a fresh briefing invalidates yesterday's/old audio
        _write(lid, briefing)

    # Surface the briefing on the loop itself (header/list/today feed) without
    # externalizing anything — this is the reviewable next step.
    if transcript or post_text or person["name"]:
        try:
            engine.apply(
                LoopCommand.from_dict(
                    {
                        "type": "update_loop",
                        "payload": {"loop_id": lid, "next_action": "Review today's briefing"},
                        "source": source,
                        "idempotency_key": f"briefing-next:{lid}:{today}"
                        + (f":{int(time.time())}" if force else ""),
                    }
                )
            )
        except Exception:
            pass

    briefing["has_audio"] = _has_audio(lid, today)
    briefing["usage"] = out.get("usage")
    return briefing


def run_active(
    loop_id: str | None = None, *, source: str = "cloud_wake", force: bool = False
) -> dict:
    """Generate a briefing for one loop (``loop_id``) or every active loop.

    This is the unit the daily scheduler calls; today it is also triggered on
    demand via ``POST /v1/briefing``.
    """
    today = date.today().isoformat()
    if loop_id:
        loop = engine.get_loop(loop_id)
        if not loop:
            raise KeyError(loop_id)
        loops = [loop]
    else:
        loops = [l for l in engine.list_loops() if l.get("status") == "active"]

    out = [
        {k: v for k, v in generate_for_loop(l, source=source, today=today, force=force).items()
         if k not in ("usage",)}
        for l in loops
    ]
    return {"date": today, "count": len(out), "briefings": out}


def get_briefing(loop_id: str) -> dict | None:
    """Return today's briefing for a loop (or None if none exists for today)."""
    data = _read(loop_id)
    if not data or data.get("date") != date.today().isoformat():
        return None
    data["has_audio"] = _has_audio(loop_id, data["date"])
    return data


# -- audio (lazy TTS) --------------------------------------------------------

def _audio_path(loop_id: str, day: str) -> str:
    return os.path.join(_audio_dir(), f"{loop_id}-{day}.mp3")


def _has_audio(loop_id: str, day: str) -> bool:
    return os.path.isfile(_audio_path(loop_id, day))


def _clear_audio(loop_id: str) -> None:
    """Remove any cached audio for this loop (all days)."""
    prefix = f"{loop_id}-"
    try:
        for name in os.listdir(_audio_dir()):
            if name.startswith(prefix) and name.endswith(".mp3"):
                try:
                    os.remove(os.path.join(_audio_dir(), name))
                except OSError:
                    pass
    except OSError:
        pass


def _tts(text: str) -> bytes:
    """Synthesize speech for ``text`` via the OpenAI TTS API (mp3 bytes)."""
    url = f"{provider.API_BASE}/audio/speech"
    body = json.dumps(
        {"model": _TTS_MODEL, "voice": _TTS_VOICE, "input": text[:4000]}
    ).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {provider.api_key()}",
        },
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            if e.code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"TTS HTTP {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < 2:
                time.sleep(2 ** attempt * 2)
                continue
            raise RuntimeError(f"TTS request failed: {e}")
    raise RuntimeError("TTS failed")


def audio_bytes(loop_id: str) -> bytes | None:
    """Return today's digest audio, synthesizing and caching it on first call.

    Returns None if there is no briefing for today or it has no transcript.
    """
    data = get_briefing(loop_id)
    if not data:
        return None
    transcript = (data.get("digest") or {}).get("transcript") or ""
    if not transcript.strip():
        return None
    day = data["date"]
    path = _audio_path(loop_id, day)
    with _lock:
        if os.path.isfile(path):
            with open(path, "rb") as f:
                return f.read()
        audio = _tts(transcript)
        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(audio)
        os.replace(tmp, path)
        return audio


# -- feedback ----------------------------------------------------------------

_ITEMS = {"digest", "post", "person"}


def record_feedback(
    loop_id: str, item: str, rating: str | None = None, dismissed: bool | None = None
) -> dict:
    """Record a rating and/or dismissal for one briefing item.

    ``item`` is one of digest|post|person; ``rating`` is up|down (or None to
    clear). Feedback tunes future briefings (stored today; used as signal).
    """
    if item not in _ITEMS:
        raise ValueError(f"item must be one of {sorted(_ITEMS)}")
    with _lock:
        data = _read(loop_id)
        if not data:
            raise KeyError(loop_id)
        fb = data.setdefault("feedback", {})
        if rating is not None:
            if rating not in ("up", "down"):
                raise ValueError("rating must be 'up' or 'down'")
            fb[item] = rating
        ds = data.setdefault("dismissed", {})
        if dismissed is not None:
            ds[item] = bool(dismissed)
        _write(loop_id, data)
    data["has_audio"] = _has_audio(loop_id, data.get("date", ""))
    return data


def todays_feed() -> list[dict]:
    """Loops that have a briefing generated today (for notification nudges)."""
    today = date.today().isoformat()
    out = []
    try:
        names = os.listdir(_briefing_dir())
    except OSError:
        return out
    for name in names:
        if not name.endswith(".json"):
            continue
        data = _read(name[: -len(".json")])
        if not data or data.get("date") != today:
            continue
        out.append(
            {
                "loop_id": data.get("loop_id"),
                "title": data.get("title"),
                "next_action": "Review today's briefing",
                "draft_id": f"briefing:{data.get('loop_id')}:{today}",
            }
        )
    return out
