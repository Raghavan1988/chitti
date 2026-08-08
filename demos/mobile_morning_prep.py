#!/usr/bin/env python3
# CLI client for the Chitti mobile harness API (SSE + approvals).
"""Demo: create a session, stream events, auto-approve calendar commits.

Usage (from repo root, server already running):

    export CHITTI_API_KEY=dev-key-change-me
    python3 demos/mobile_morning_prep.py

    # custom task:
    python3 demos/mobile_morning_prep.py "Prep my day and block 30m for email"
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.request

BASE = os.environ.get("CHITTI_BASE", "http://127.0.0.1:8787")
KEY = os.environ.get("CHITTI_API_KEY", "dev-key-change-me")
AUTO_APPROVE = os.environ.get("CHITTI_AUTO_APPROVE", "1") not in ("0", "false", "no")


def _req(method: str, path: str, body: dict | None = None) -> dict:
    data = None if body is None else json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=600) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _sse_loop(session_id: str, stop: threading.Event):
    """Read SSE until turn_complete or stop."""
    request = urllib.request.Request(
        BASE + f"/v1/sessions/{session_id}/events",
        headers={"Authorization": f"Bearer {KEY}", "Accept": "text/event-stream"},
    )
    with urllib.request.urlopen(request, timeout=600) as resp:
        event_name = "message"
        data_lines: list[str] = []
        while not stop.is_set():
            line = resp.readline()
            if not line:
                break
            text = line.decode("utf-8", errors="replace").rstrip("\n")
            if text.startswith(":"):
                continue
            if text.startswith("event:"):
                event_name = text[6:].strip()
                continue
            if text.startswith("data:"):
                data_lines.append(text[5:].lstrip())
                continue
            if text == "" and data_lines:
                raw = "\n".join(data_lines)
                data_lines = []
                try:
                    payload = json.loads(raw)
                except json.JSONDecodeError:
                    print(f"  (bad sse json) {raw[:200]}")
                    event_name = "message"
                    continue
                _print_event(session_id, event_name, payload)
                kind = payload.get("kind") or event_name
                if kind in ("turn_complete", "done", "error"):
                    if kind == "turn_complete":
                        stop.set()
                        break
                event_name = "message"


def _print_event(session_id: str, event_name: str, payload: dict):
    kind = payload.get("kind") or event_name
    body = payload.get("payload", payload)
    if kind == "hello":
        print(f"— stream open ({session_id[:8]}…)")
    elif kind == "user":
        print(f"\nYou: {body.get('text', '')}")
    elif kind == "assistant":
        text = (body.get("text") or "").strip()
        calls = body.get("tool_calls") or []
        if text:
            print(f"\nChitti: {text}")
        for c in calls:
            print(f"  → tool {c.get('name')}({json.dumps(c.get('args') or {}, ensure_ascii=False)})")
    elif kind == "tool_start":
        print(f"  … running {body.get('name')} …")
    elif kind == "tool_end":
        result = str(body.get("result", ""))[:300]
        name = (body.get("call") or {}).get("name", "?")
        print(f"  ← {name}: {result}")
    elif kind == "approval_required":
        aid = body.get("id")
        reason = body.get("reason")
        print(f"\n⚠ approval required: {reason} [{aid}]")
        if AUTO_APPROVE:
            try:
                _req(
                    "POST",
                    f"/v1/sessions/{session_id}/approvals/{aid}",
                    {"approved": True},
                )
                print("  ✓ auto-approved")
            except urllib.error.HTTPError as e:
                print(f"  ✗ approve failed: {e}")
        else:
            print("  (set CHITTI_AUTO_APPROVE=1 or POST approvals from another client)")
    elif kind == "done":
        print(f"\n=== final ===\n{body.get('text', '')}\n")
    elif kind == "error":
        print(f"\nERROR: {body.get('message')}")
    elif kind == "turn_complete":
        print("— turn complete")
    else:
        print(f"  [{kind}] {json.dumps(body, ensure_ascii=False)[:240]}")


def main():
    task = " ".join(sys.argv[1:]).strip() or (
        "Prep my day. Load the morning_prep skill. Summarize my calendar, "
        "remember that I prefer no meetings before 10am, and propose a 25-minute "
        "email block this afternoon if there is a free gap. If you commit anything, "
        "wait for approval."
    )
    print(f"Base: {BASE}")
    try:
        health = _req("GET", "/health") if False else None
    except Exception:
        pass
    # health is public-ish but still check server
    try:
        request = urllib.request.Request(BASE + "/health")
        with urllib.request.urlopen(request, timeout=5) as resp:
            print("health:", resp.read().decode())
    except Exception as e:
        print(f"Cannot reach server at {BASE}: {e}")
        print("Start it with:  python3 -m server")
        sys.exit(1)

    sess = _req("POST", "/v1/sessions", {"label": "morning-prep"})
    sid = sess["id"]
    print(f"session: {sid}")

    stop = threading.Event()
    t = threading.Thread(target=_sse_loop, args=(sid, stop), daemon=True)
    t.start()
    # Give SSE a moment to connect
    import time

    time.sleep(0.3)
    _req("POST", f"/v1/sessions/{sid}/messages", {"text": task})
    t.join(timeout=600)
    if not stop.is_set():
        print("(timed out waiting for turn_complete)")


if __name__ == "__main__":
    main()
