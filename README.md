# Odysseus

A minimal agent harness in Python — standard library only, no third-party
packages, Python 3.10+. Built as a reference implementation, one day at a time.

An *agent* here is a conversation that runs itself: the harness calls a model,
executes any tools the model asks for, feeds the results back, and repeats until
the model answers in plain text.

## Layout

```
odysseus/          the harness package
  provider.py      the only file that knows about the model (Gemini) — HTTP,
                   wire format, and the Gemini 3 thoughtSignature round-trip
  loop.py          the agent loop: model -> tools -> results -> repeat
  __init__.py      package marker (filled in on a later day)
demos/             runnable examples
  day1_dice.py     the smallest complete agent: one tool, one loop, one answer
```

Everything outside `provider.py` speaks a small, neutral message format and
never touches HTTP or vendor-specific JSON. Swap the provider and the rest of
the harness follows a different model unchanged.

### Neutral message format

- `{"role": "user", "text"}`
- `{"role": "assistant", "text", "tool_calls"}`
- `{"role": "tool", "name", "text"}`

### Tools

A tool is any object with two attributes:

- `.spec` — the schema the model sees, shaped `{"schema": {...}}`
- `.run` — a callable invoked with the model's arguments as keywords

The loop never crashes because of a tool: unknown names and raised exceptions
become tool results the model can read and recover from, not tracebacks.

## Setup

Set an API key before running anything:

```bash
export ODYSSEUS_API_KEY=...   # or GEMINI_API_KEY
```

## Running the demo

```bash
python3 demos/day1_dice.py
```

This rolls three dice through a hand-written `roll_dice` tool and reports whether
the total beats 10, printing a trace of each step: the user prompt, the
assistant's tool call, the tool result, and the final answer.
