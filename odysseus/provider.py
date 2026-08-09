# The OpenAI client: the only file that speaks HTTP and vendor wire format.
"""Day 1 — the provider: the single seam between Odysseus and the model.

Concept: every other file in the harness speaks a small, neutral message
format and never touches HTTP, JSON wire shapes, or vendor quirks. This file
is the only place that knows about OpenAI. Swap this file and the rest of the
harness follows a different model unchanged.

Design rules:
  - Neutral in, neutral out. The loop hands us plain dicts; we hand back a
    plain dict {"text", "tool_calls", "usage"}. No wire types escape.
  - Stable tool identity. OpenAI pairs each tool result to its call by
    `tool_call_id`. We stash the id the model gave each call on the neutral
    tool_call (its "signature") and replay it, so multi-turn tool use stays
    valid across the round-trip.
  - Fail loud on real errors, retry the transient ones. A 429 is weather; a
    400 is a bug — only one of them deserves patience.
"""

import json
import os
import time
import urllib.error
import urllib.request

API_BASE = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1").rstrip("/")
API_URL = f"{API_BASE}/chat/completions"
DEFAULT_MODEL = "gpt-4o-mini"


def api_key():
    """Return the API key, preferring ODYSSEUS_API_KEY over OPENAI_API_KEY.

    Raise RuntimeError when neither is set so misconfiguration surfaces at the
    first call rather than as an opaque 401 from the wire.
    """
    key = os.environ.get("ODYSSEUS_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "No API key: set ODYSSEUS_API_KEY (or OPENAI_API_KEY)."
        )
    return key


def _to_wire(messages):
    """Translate neutral messages into OpenAI chat `messages`.

    user -> user message. assistant -> assistant message carrying its text plus
    one tool_call per neutral tool_call (arguments serialized to a JSON string,
    the id taken from the call's stored signature). tool -> a tool message whose
    `tool_call_id` is matched positionally to the preceding assistant's calls:
    the loop always appends one tool result per call, in order, so a small queue
    pairs them the way OpenAI requires.
    """
    wire = []
    pending_ids = []
    for m in messages:
        role = m["role"]
        if role == "user":
            wire.append({"role": "user", "content": m["text"]})
        elif role == "assistant":
            calls = m.get("tool_calls", [])
            msg = {"role": "assistant", "content": m.get("text") or ""}
            pending_ids = []
            if calls:
                tool_calls = []
                for i, call in enumerate(calls):
                    cid = call.get("signature") or f"call_{i}"
                    pending_ids.append(cid)
                    tool_calls.append({
                        "id": cid,
                        "type": "function",
                        "function": {
                            "name": call["name"],
                            "arguments": json.dumps(call.get("args", {})),
                        },
                    })
                msg["tool_calls"] = tool_calls
                # OpenAI wants null content when the turn is only tool calls.
                if not m.get("text"):
                    msg["content"] = None
            wire.append(msg)
        elif role == "tool":
            cid = pending_ids.pop(0) if pending_ids else "call_0"
            wire.append({"role": "tool", "tool_call_id": cid, "content": m["text"]})
    return wire


def complete(model, system, messages, tools):
    """Call the model once and return {"text", "tool_calls", "usage"}.

    `tools` is a list of spec dicts, each shaped {"schema": ...}; we wrap each
    schema as an OpenAI function tool. The model may answer with text, with tool
    calls, or both; every returned call keeps its OpenAI id as its signature so
    the next turn can pair the tool result back to it.
    """
    wire = [{"role": "system", "content": system}] + _to_wire(messages)
    body = {"model": model, "messages": wire, "temperature": 0.4}
    if tools:
        body["tools"] = [{"type": "function", "function": t["schema"]} for t in tools]
        body["tool_choice"] = "auto"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key()}",
    }
    data = _post(API_URL, body, headers)

    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message", {})
    text = message.get("content") or ""
    tool_calls = []
    for tc in message.get("tool_calls") or []:
        fn = tc.get("function", {})
        try:
            args = json.loads(fn.get("arguments") or "{}")
        except json.JSONDecodeError:
            # A malformed argument blob is data the model can recover from, not
            # a crash: hand the tool an empty mapping and let it report back.
            args = {}
        tool_calls.append({"name": fn.get("name"), "args": args,
                           "signature": tc.get("id")})

    usage = data.get("usage", {})
    return {"text": text, "tool_calls": tool_calls, "usage": {
        "input": usage.get("prompt_tokens", 0),
        "output": usage.get("completion_tokens", 0)}}


def _post(url, body, headers, retries=5):
    """POST JSON and return the parsed response, retrying transient failures.

    429/500/502/503 and connection errors get exponential backoff
    (2**attempt * 2 seconds); every other HTTP status is a permanent error and
    raises immediately with the status and the head of the error body.
    """
    payload = json.dumps(body).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload, headers=headers)
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
