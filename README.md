# Odysseus

A minimal agent harness in Python — standard library only, no third-party
packages, Python 3.10+. Built as a reference implementation, one day at a time.

An *agent* here is a conversation that runs itself: the harness calls a model,
executes any tools the model asks for, feeds the results back, and repeats until
the model answers in plain text.

## Layout

```
odysseus/          the coding-agent harness package
  provider.py      the only file that knows about the model (Gemini) — HTTP,
                   wire format, and the Gemini 3 thoughtSignature round-trip
  loop.py          the agent loop: model -> tools -> results -> repeat, with
                   on_event / before_tool / before_turn sockets
  tools.py         the Tool type, the @tool decorator, and the six core tools
                   (read/write/edit/bash/list/grep) jailed to a working directory
  security.py      Policy (read-only / safe / yolo) and always-on deny rules
  context.py       token estimation and compaction on the before_turn socket
  memory.py        the base system prompt and durable ODYSSEUS.md project memory
  skills.py        on-demand procedures loaded from skills/<name>/SKILL.md
  harness.py       composes the full coding agent
server/            iPhone harness API (life-ops tools, SSE, approvals)
mobile/ios/        SwiftUI thin client (chat, voice, approvals)
skills/            shared skill packs (e.g. morning_prep)
plan.md            iPhone harness product + delivery plan
demos/             runnable examples
  day1_dice.py     the smallest complete agent: one tool, one loop, one answer
  day2_build.py    a coding agent with hands: build, run, and refuse safely
  day3_context.py  compaction, cross-conversation memory, and a voice skill
  mobile_morning_prep.py  CLI client for the mobile harness API
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

The `@tool` decorator in `tools.py` derives the schema from a function's
signature — argument names become parameters, and those without a default are
required. `core_tools(workdir)` returns six tools closed over a single
`resolve()` gate, so no tool can touch a file outside the working directory.

The loop never crashes because of a tool: unknown names and raised exceptions
become tool results the model can read and recover from, not tracebacks.

### Security

`Policy(mode, approver)` fills the loop's `before_tool` socket. Modes are
`read-only` (only `read_file`, `list_files`, `grep`), `safe` (writes and
commands ask an approver), and `yolo` (trust everything). A set of deny patterns
— wiping `/`, `~`, or `$HOME`, `sudo`, `curl | sh`, force-pushes, raw-disk
writes — is refused in **every** mode. A blocked call becomes a `BLOCKED: ...`
tool result the model reads and works around, never a crash.

### Context, memory, and skills

- **Context.** `compact()` rides the `before_turn` socket: when the message
  list outgrows its token budget it folds the old turns into one dense summary
  and keeps the recent tail verbatim, so a long run stays inside the window.
- **Memory.** `build_system_prompt()` gives Odysseus its character and folds in
  `ODYSSEUS.md` when present. `remember()` appends a note to that file, so a fact
  learned on one run is read back on every future run over the same directory —
  even in a brand-new conversation with no shared history.
- **Skills.** A skill is a `skills/<name>/SKILL.md` procedure. The catalog
  advertises what exists in the system prompt; a `use_skill` tool pulls the full
  text in only when relevant, so knowledge scales without bloating every prompt.

## Setup

Set an API key before running anything:

```bash
export ODYSSEUS_API_KEY=...   # or GEMINI_API_KEY
```

## Running the demos

```bash
python3 demos/day1_dice.py       # one tool, one loop, one answer
python3 demos/day2_build.py      # build fib.py, then refuse a dangerous command
python3 demos/day3_context.py    # compaction, durable memory, and a skill
```

`day1_dice.py` rolls three dice through a hand-written `roll_dice` tool and
reports whether the total beats 10. `day2_build.py` writes and runs a program in
a scratch directory, then shows the policy blocking a home-directory wipe and the
path jail catching an escape attempt. `day3_context.py` runs a long task that
trips compaction mid-run, proves a remembered fact survives into a fresh
conversation, and lets a `brand-voice` skill change the agent's voice with zero
code changes. Each demo prints a trace of every step: the user prompt, the
assistant's tool calls, the tool results, and the final answer.

## Mobile harness (iPhone)

Hybrid agent for tasks Siri is weak at: chat/voice UI on the phone, harness on
your machine. See `plan.md` and `server/README.md`.

```bash
export ODYSSEUS_API_KEY=...          # model
export CHITTI_API_KEY=dev-key-change-me
python3 -m server                    # http://0.0.0.0:8787

# other terminal
export CHITTI_API_KEY=dev-key-change-me
python3 demos/mobile_morning_prep.py
```

SwiftUI sources live under `mobile/ios/Chitti/` — open via a new Xcode app
project on a Mac (see `mobile/ios/README.md`).
