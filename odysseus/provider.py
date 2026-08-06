# The Gemini client: the only file that speaks HTTP and vendor wire format.
"""Day 1 — the provider: the single seam between Odysseus and the model.

Concept: every other file in the harness speaks a small, neutral message
format and never touches HTTP, JSON wire shapes, or vendor quirks. This file
is the only place that knows about Gemini. Swap this file and the rest of the
harness follows a different model unchanged.

Design rules:
  - Neutral in, neutral out. The loop hands us plain dicts; we hand back a
    plain dict {"text", "tool_calls", "usage"}. No wire types escape.
  - One round-trip contract. Gemini 3 issues a `thoughtSignature` with every
    function call and requires it echoed back verbatim on the next turn, or it
    rejects the continuation. We store it on the tool call and replay it.
  - Fail loud on real errors, retry the transient ones. A 429 is weather; a
    400 is a bug — only one of them deserves patience.
"""

import json
import os
import time
import urllib.error
import urllib.request

API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-3.1-pro-preview"


def api_key():
    """Return the API key, preferring ODYSSEUS_API_KEY over GEMINI_API_KEY.

    Raise RuntimeError when neither is set so misconfiguration surfaces at the
    first call rather than as an opaque 401 from the wire.
    """
    key = os.environ.get("ODYSSEUS_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "No API key: set ODYSSEUS_API_KEY (or GEMINI_API_KEY)."
        )
    return key


def _to_wire(messages):
    """Translate neutral messages into Gemini `contents` parts.

    user -> user turn, one text part. assistant -> "model" turn: a text part
    (when non-empty) plus one functionCall part per tool call, each echoing the
    stored signature as `thoughtSignature` (the Gemini 3 round-trip that keeps a
    multi-turn tool conversation valid). tool -> user turn with a functionResponse.
    """
    wire = []
    for m in messages:
        role = m["role"]
        if role == "user":
            wire.append({"role": "user", "parts": [{"text": m["text"]}]})
        elif role == "assistant":
            parts = [{"text": m["text"]}] if m.get("text") else []
            for call in m.get("tool_calls", []):
                part = {"functionCall": {"name": call["name"], "args": call["args"]}}
                # Echo the signature Gemini gave us, or the model rejects the turn.
                if call.get("signature"):
                    part["thoughtSignature"] = call["signature"]
                parts.append(part)
            wire.append({"role": "model", "parts": parts})
        elif role == "tool":
            wire.append({"role": "user", "parts": [{"functionResponse": {
                "name": m["name"], "response": {"result": m["text"]}}}]})
    return wire


def complete(model, system, messages, tools):
    """Call the model once and return {"text", "tool_calls", "usage"}.

    `tools` is a list of spec dicts, each shaped {"schema": ...}; we pass the
    schemas through as functionDeclarations. Parts flagged as "thought" are
    the model's private reasoning and are dropped from the visible text.
    """
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": _to_wire(messages),
        "generationConfig": {"temperature": 0.4, "maxOutputTokens": 65536},
    }
    if tools:
        body["tools"] = [{"functionDeclarations": [t["schema"] for t in tools]}]

    url = f"{API_ROOT}/{model}:generateContent?key={api_key()}"
    data = _post(url, body)

    candidates = data.get("candidates", [])
    parts = candidates[0]["content"]["parts"] if candidates else []
    text, tool_calls = "", []
    for part in parts:
        if "functionCall" in part:
            fc = part["functionCall"]
            tool_calls.append({"name": fc["name"], "args": fc.get("args", {}),
                               "signature": part.get("thoughtSignature")})
        elif "text" in part and not part.get("thought"):
            text += part["text"]

    usage = data.get("usageMetadata", {})
    return {"text": text, "tool_calls": tool_calls, "usage": {
        "input": usage.get("promptTokenCount", 0),
        "output": usage.get("candidatesTokenCount", 0)}}


def _post(url, body, retries=5):
    """POST JSON and return the parsed response, retrying transient failures.

    429/500/502/503 and connection errors get exponential backoff
    (2**attempt * 2 seconds); every other HTTP status is a permanent error and
    raises immediately with the status and the head of the error body.
    """
    payload = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(
            url, data=payload, headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            detail = e.read().decode("utf-8", "replace")[:400]
            raise RuntimeError(f"HTTP {e.code}: {detail}")
        except (urllib.error.URLError, TimeoutError):
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            raise
