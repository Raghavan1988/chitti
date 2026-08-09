# The agent loop: call model, run the tools it asks for, repeat until an answer.
"""Day 1 — the agent loop: turn a model into an agent.

Concept: an agent is a conversation that runs itself. The loop calls the
model, executes any tools it asks for, feeds the results back, and repeats
until the model answers in plain text. Nothing here is provider-specific — it
speaks only the neutral message format and the provider's return shape.

Design rules:
  - The loop never crashes on a tool. Unknown names and raised exceptions
    become tool results the model can read and recover from, not tracebacks.
  - Events, not prints. on_event lets callers watch the run without the loop
    deciding how anything is displayed.
  - Every hook stays out of the way until asked. before_turn is threaded now
    but idle until day 3 wires compaction into it.
"""

from . import provider


def run_loop(model, system, messages, tools, on_event, before_tool,
             max_turns=80, before_turn=None):
    """Drive the model-tool conversation to a final text answer.

    tools maps name -> Tool, where a Tool has .spec ({"schema": ...}) and .run
    (a callable taking keyword args). on_event(kind, payload) fires "assistant"
    after each reply and "tool_start"/"tool_end" around each execution.
    before_tool(call) returns None to allow or a reason string to block.
    before_turn, when given, may rewrite the message list in place before each
    model call — unused today, the seam day 3 fills with compaction.
    """
    specs = [t.spec for t in tools.values()]

    for _ in range(max_turns):
        if before_turn:
            # Return value replaces the list so compaction can shrink history.
            messages = before_turn(messages)

        reply = provider.complete(model, system, messages, specs)
        messages.append({
            "role": "assistant",
            "text": reply["text"],
            "tool_calls": reply["tool_calls"],
        })
        on_event("assistant", reply)

        if not reply["tool_calls"]:
            return reply["text"]

        for call in reply["tool_calls"]:
            on_event("tool_start", call)
            reason = before_tool(call)
            if reason is not None:
                result = f"BLOCKED: {reason}"
            elif call["name"] not in tools:
                result = f"ERROR: unknown tool {call['name']}"
            else:
                try:
                    result = tools[call["name"]].run(**call["args"])
                except Exception as e:
                    # A failing tool is data for the model, never a crash.
                    result = f"ERROR: {type(e).__name__}: {e}"
            messages.append({"role": "tool", "name": call["name"], "text": str(result)})
            on_event("tool_end", {"call": call, "result": result})

    # Out of turns: strip tools and demand a closing answer.
    messages.append({"role": "user", "text": "Turn limit reached; wrap up now."})
    final = provider.complete(model, system, messages, [])
    messages.append({"role": "assistant", "text": final["text"], "tool_calls": []})
    return final["text"]
