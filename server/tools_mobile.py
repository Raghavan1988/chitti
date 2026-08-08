# Life-ops tools for the iPhone harness (no bash / free filesystem).
"""Mobile tools: calendar fixture, drafts, notes, durable memory.

These replace Odysseus core_tools for the phone product. Side-effecting
commits go through the approval gate so the model never silently writes.
"""

from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from odysseus.tools import tool

if TYPE_CHECKING:
    from .approvals import ApprovalGate

MEMORY_FILE = "CHITTI.md"
NOTES_FILE = "notes.md"
DRAFTS_DIR = "drafts"
CALENDAR_STATE = ".chitti/calendar_events.json"


def _read_json(path: Path, default):
    if not path.is_file():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_calendar_fixture(fixture_path: Path) -> list[dict]:
    """Load the seed calendar; shift fixed dates to *today* so demos always have events."""
    data = _read_json(fixture_path, {"events": []})
    events = list(data.get("events", []))
    return _rebase_events_to_today(events)


def _rebase_events_to_today(events: list[dict]) -> list[dict]:
    """Map fixture days onto the current local date while keeping clock times."""
    from datetime import datetime, timedelta

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    parsed: list[tuple[datetime, dict]] = []
    for ev in events:
        raw = ev.get("start") or ""
        try:
            start_dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            continue
        parsed.append((start_dt, ev))
    if not parsed:
        return events
    base_day = min(dt for dt, _ in parsed).replace(hour=0, minute=0, second=0, microsecond=0)
    out = []
    for start_dt, ev in parsed:
        delta_days = (start_dt.date() - base_day.date()).days
        new_start = today + timedelta(days=delta_days, hours=start_dt.hour, minutes=start_dt.minute)
        end_raw = ev.get("end") or ""
        try:
            end_dt = datetime.fromisoformat(str(end_raw).replace("Z", "+00:00")).replace(tzinfo=None)
            end_delta = end_dt - start_dt
            new_end = new_start + end_delta
            end_s = new_end.isoformat(timespec="minutes")
        except ValueError:
            end_s = ev.get("end", "")
        cloned = dict(ev)
        cloned["start"] = new_start.isoformat(timespec="minutes")
        cloned["end"] = end_s
        cloned["start_ts"] = new_start.timestamp()
        out.append(cloned)
    return out


def mobile_tools(workdir: str, gate: ApprovalGate, fixture_path: Path):
    """Build the v1 tool list closed over workdir + approval gate."""
    root = Path(os.path.realpath(workdir))
    root.mkdir(parents=True, exist_ok=True)
    state_path = root / CALENDAR_STATE

    # Always refresh seed when missing or still empty of upcoming events.
    if not state_path.is_file():
        _write_json(state_path, {"events": load_calendar_fixture(fixture_path)})

    @tool(
        "Save a durable preference or fact about the user (CHITTI.md)",
        note="the fact to remember across future sessions",
    )
    def remember(note):
        path = root / MEMORY_FILE
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"- {note}\n")
        return f"Remembered in {MEMORY_FILE}"

    @tool(
        "List calendar events for the next N days (fixture or committed state)",
        days="how many days ahead to include, default 2",
    )
    def calendar_list(days="2"):
        try:
            n = max(1, min(14, int(float(days))))
        except ValueError:
            n = 2
        from datetime import datetime, timedelta

        start_of_today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        horizon = start_of_today + timedelta(days=n)
        lo, hi = start_of_today.timestamp(), horizon.timestamp()
        events = _read_json(state_path, {"events": []}).get("events", [])
        upcoming = []
        for ev in events:
            ts = _to_ts(ev.get("start_ts") or ev.get("start"))
            if ts is None or lo <= ts < hi:
                upcoming.append(ev)
        upcoming.sort(key=lambda e: _to_ts(e.get("start_ts") or e.get("start")) or 0)
        if not upcoming:
            return "(no events in range)"
        lines = []
        for ev in upcoming:
            lines.append(
                f"- {ev.get('start', ev.get('start_ts'))} | {ev.get('title')} "
                f"@ {ev.get('location', '—')} [{ev.get('id', '?')}]"
            )
        return "\n".join(lines)

    @tool(
        "Propose a calendar event as a draft JSON (does not write the calendar)",
        title="event title",
        start="local start time, ISO-8601 preferred",
        end="local end time, ISO-8601 preferred",
        location="optional location",
        notes="optional notes",
    )
    def calendar_propose_event(title, start, end, location="", notes=""):
        draft = {
            "id": f"prop-{uuid.uuid4().hex[:8]}",
            "title": title,
            "start": start,
            "end": end,
            "location": location,
            "notes": notes,
            "status": "proposed",
        }
        return json.dumps(draft, ensure_ascii=False)

    @tool(
        "Commit a proposed calendar event after user approval",
        title="event title",
        start="local start time",
        end="local end time",
        location="optional location",
        notes="optional notes",
    )
    def calendar_commit_event(title, start, end, location="", notes=""):
        call = {
            "name": "calendar_commit_event",
            "args": {
                "title": title,
                "start": start,
                "end": end,
                "location": location,
                "notes": notes,
            },
        }
        decision = gate.request(call, f"create calendar event: {title} @ {start}")
        if decision != "approved":
            return f"BLOCKED: calendar commit {decision}"
        event = {
            "id": f"evt-{uuid.uuid4().hex[:8]}",
            "title": title,
            "start": start,
            "end": end,
            "start_ts": _to_ts(start),
            "location": location,
            "notes": notes,
            "status": "committed",
        }
        data = _read_json(state_path, {"events": []})
        data.setdefault("events", []).append(event)
        _write_json(state_path, data)
        return json.dumps({"ok": True, "event": event}, ensure_ascii=False)

    @tool(
        "Store a message draft for the user to send manually (never auto-sends)",
        to="recipient name or address",
        subject="subject line",
        body="full message body",
    )
    def draft_message(to, subject, body):
        drafts = root / DRAFTS_DIR
        drafts.mkdir(exist_ok=True)
        draft_id = f"draft-{uuid.uuid4().hex[:8]}"
        path = drafts / f"{draft_id}.json"
        payload = {
            "id": draft_id,
            "to": to,
            "subject": subject,
            "body": body,
            "created_at": time.time(),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        return json.dumps({"ok": True, "draft": payload}, ensure_ascii=False)

    @tool(
        "Append a line to the user's running notes file",
        text="text to append",
    )
    def notes_append(text):
        call = {"name": "notes_append", "args": {"text": text}}
        decision = gate.request(call, "append to notes.md")
        if decision != "approved":
            return f"BLOCKED: notes append {decision}"
        path = root / NOTES_FILE
        with open(path, "a", encoding="utf-8") as f:
            f.write(text.rstrip() + "\n")
        return f"Appended to {NOTES_FILE}"

    return [
        remember,
        calendar_list,
        calendar_propose_event,
        calendar_commit_event,
        draft_message,
        notes_append,
    ]


def _to_ts(value):
    """Best-effort parse of epoch float/int or ISO date/time to epoch seconds."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    try:
        return float(s)
    except ValueError:
        pass
    try:
        from datetime import datetime

        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return None
