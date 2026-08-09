# Durable JSONL sessions with crash repair, for --resume across restarts.
"""Day 4 — session: the agent's durable memory of a single run.

Concept: every message is appended to a JSONL file as it lands, so a run can be
resumed after the process dies. Crashes are the normal case, not the exception —
the model may be mid-tool-call when the power cuts — so load() tolerates a torn
final line and repairs a dangling tool call into a valid transcript.

Design rules:
  - Append-only and line-oriented. One JSON object per line means a crash can
    only ever corrupt the last line, never the history before it.
  - Always return a valid transcript. OpenAI rejects an assistant tool call with
    no matching tool result; repair() manufactures the missing results so a
    resumed conversation is well-formed on the first turn.
"""

import json
import os
import re
import time

SESSION_DIR = ".odysseus/sessions"


def _dir(workdir):
    """The absolute session directory for a workspace."""
    return os.path.join(os.path.realpath(workdir), SESSION_DIR)


def new_session(workdir, label="session"):
    """Create the session directory and return a fresh timestamped log path.

    The label is slugified to alphanumerics and dashes and clipped to 40 chars
    so the filename stays readable and safe on any filesystem.
    """
    directory = _dir(workdir)
    os.makedirs(directory, exist_ok=True)
    slug = re.sub(r"[^a-zA-Z0-9-]+", "-", label).strip("-")[:40] or "session"
    return os.path.join(directory, f"{int(time.time())}-{slug}.jsonl")


def append(path, message):
    """Append one message as a JSON line, preserving non-ASCII text verbatim."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(message, ensure_ascii=False) + "\n")


def load(path):
    """Read a session back, stopping at the first torn line, then repair it."""
    messages = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                # A half-written final line means the process died here; keep
                # everything before it and stop.
                break
    _repair(messages)
    return messages


def latest(workdir):
    """Return the most recently modified .jsonl session, or None if there is none."""
    directory = _dir(workdir)
    if not os.path.isdir(directory):
        return None
    files = [os.path.join(directory, f) for f in os.listdir(directory)
             if f.endswith(".jsonl")]
    return max(files, key=os.path.getmtime) if files else None


def _repair(messages):
    """Give every dangling tool call a result so the transcript is well-formed.

    Find the last assistant turn, count the tool results that already follow it,
    and synthesize an "interrupted" result for each of its tool calls beyond that
    count — the exact pairing OpenAI requires to accept the next turn.
    """
    last = None
    for i in range(len(messages) - 1, -1, -1):
        if messages[i].get("role") == "assistant":
            last = i
            break
    if last is None:
        return

    calls = messages[last].get("tool_calls", [])
    responded = sum(1 for m in messages[last + 1:] if m.get("role") == "tool")
    for call in calls[responded:]:
        messages.append({
            "role": "tool", "name": call["name"],
            "text": "Interrupted before this ran (process restarted).",
        })
