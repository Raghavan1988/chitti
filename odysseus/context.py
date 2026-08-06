# Token estimation and conversation compaction to stay within the context window.
"""Day 3 — context: keep the conversation inside the model's window.

Concept: a long agent run grows an unbounded message list; eventually it will
not fit. compact() is the before_turn hook the loop already threads — it folds
the old turns into one dense summary and keeps only the recent slice verbatim,
so the run continues without the model losing the thread.

Design rules:
  - Cheap, then careful. estimate_tokens is a length heuristic; we only pay for
    a summarization call once it says the budget is blown.
  - The recent tail stays untouched. Summaries lose fidelity, so the last few
    turns are preserved exactly — that is where the model is actively working.
  - Never hand back an orphaned tool result. A tool message with no preceding
    call confuses the model, so leading tool messages are trimmed off the tail.
"""

from . import provider

CHARS_PER_TOKEN = 4
KEEP_RECENT = 6

_CLIP = 2000
_SYSTEM = (
    "You compress agent transcripts. Preserve: the original task, every file "
    "created or edited and its purpose, key decisions, unresolved errors, and "
    "what remains to be done. Be dense and factual."
)


def estimate_tokens(messages):
    """Roughly estimate the token cost of a message list by character length."""
    return sum(len(str(m)) for m in messages) // CHARS_PER_TOKEN


def _render(messages):
    """Render old messages into a plain transcript for the summarizer.

    Each line names the role (and the tool for tool results), includes the text
    clipped to keep the transcript bounded, and names any tool calls the
    assistant made so the summary can account for actions, not just words.
    """
    lines = []
    for m in messages:
        role = m["role"]
        text = (m.get("text") or "")[:_CLIP]
        if role == "tool":
            lines.append(f"[tool {m.get('name', '')}] {text}")
        elif role == "assistant":
            lines.append(f"[assistant] {text}")
            for call in m.get("tool_calls", []):
                lines.append(f"  -> calls {call['name']}({call.get('args', {})})")
        else:
            lines.append(f"[{role}] {text}")
    return "\n".join(lines)


def compact(model, messages, budget_tokens):
    """Fold old turns into one summary when the list outgrows budget_tokens.

    Returns the list unchanged while it fits the budget, or is short enough that
    there is nothing to gain. Otherwise it summarizes everything but the last
    KEEP_RECENT messages and returns [one compacted-summary user message] + the
    recent tail, with any leading orphaned tool results trimmed from that tail.
    """
    if estimate_tokens(messages) <= budget_tokens or len(messages) <= KEEP_RECENT + 1:
        return messages

    old = messages[:-KEEP_RECENT]
    recent = messages[-KEEP_RECENT:]
    # A tool result with no preceding assistant call is orphaned once its call
    # lands in the summary — drop such leaders so the tail starts clean.
    while recent and recent[0]["role"] == "tool":
        recent = recent[1:]

    reply = provider.complete(model, _SYSTEM,
                              [{"role": "user", "text": _render(old)}], [])
    summary = {"role": "user",
               "text": f"[Conversation so far, compacted]\n{reply['text']}"}
    return [summary] + recent
