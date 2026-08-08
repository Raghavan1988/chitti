# Chitti / Odysseus

Two harnesses in one repo:

1. **Odysseus** — minimal **coding** agent harness in Python (stdlib only).
2. **Chitti** — **iPhone** personal-ops agent: SwiftUI app + Python server, for
   multi-step tasks Siri is weak at (day prep, drafts, memory, confirm-before-write).

An *agent* is a conversation that runs itself: call a model, run tools, feed
results back, repeat until the model answers in plain text.

---

## Quick start: test on a real iPhone (Mac + device)

Clone this repo on a **Mac**, run the harness, install the app to your iPhone.

### A. Server on the Mac

```bash
git clone https://github.com/Raghavan1988/chitti.git
cd chitti

export ODYSSEUS_API_KEY=your_key_here   # or GEMINI_API_KEY
export CHITTI_API_KEY=dev-key-change-me

chmod +x scripts/*.sh
./scripts/run-server.sh
```

Note the printed **LAN URL** (e.g. `http://192.168.1.42:8787`). Keep this process running.

Optional: copy `.env.example` → `.env` and fill keys instead of exporting.

### B. iOS app → physical iPhone

```bash
open mobile/ios/Chitti.xcodeproj
```

1. **Signing & Capabilities** → your Apple ID **Team** (automatic signing).
2. Change **Bundle Identifier** if needed (`com.chitti.app` → unique id).
3. Connect the iPhone (USB), unlock, trust the computer.
4. Select the **iPhone** as run destination → **Run** (▶).
5. On device: **Settings → General → VPN & Device Management** → trust your cert.

### C. App Settings (on the phone)

| Setting | Value |
|---------|--------|
| Base URL | `http://<mac-lan-ip>:8787` (from `run-server.sh`) |
| API key | same as `CHITTI_API_KEY` (default `dev-key-change-me`) |

**Do not use `127.0.0.1` on a physical iPhone** — that points at the phone itself.
Simulator may use `http://127.0.0.1:8787`.

### D. Try it

Chat:

```text
Prep my day. Load the morning_prep skill and summarize my calendar.
```

Or use the mic. Approve calendar/note writes when the card appears.

Full iOS notes: [`mobile/ios/README.md`](mobile/ios/README.md).  
Server API: [`server/README.md`](server/README.md).  
Product plan: [`plan.md`](plan.md).

```
┌─────────────┐  Wi‑Fi HTTP/SSE   ┌──────────────────────┐  HTTPS  ┌─────────┐
│  iPhone app │ ───────────────► │ python3 -m server    │ ──────► │  Model  │
│  chat/voice │                  │ tools + approvals    │         │  API    │
└─────────────┘                  └──────────────────────┘         └─────────┘
```

---

## Layout

```
odysseus/              coding-agent harness (Python stdlib)
server/                Chitti mobile harness HTTP API + life-ops tools
mobile/ios/            Xcode project + SwiftUI client
  Chitti.xcodeproj/    open this on a Mac
  Chitti/              app sources
skills/                shared skill packs (e.g. morning_prep)
scripts/
  run-server.sh        start harness + print LAN URL for iPhone
  smoke-api.sh         health check (no model call)
demos/                 day1–3 coding demos + mobile_morning_prep.py
plan.md                iPhone harness product plan
.env.example           env vars for server + model
```

---

## Odysseus (coding agent)

Standard library only, Python 3.10+. Built as a reference implementation.

### Neutral message format

- `{"role": "user", "text"}`
- `{"role": "assistant", "text", "tool_calls"}`
- `{"role": "tool", "name", "text"}`

Everything outside `provider.py` uses this format and never touches vendor HTTP.

### Setup

```bash
export ODYSSEUS_API_KEY=...   # or GEMINI_API_KEY
```

### Coding demos

```bash
python3 demos/day1_dice.py       # one tool, one loop, one answer
python3 demos/day2_build.py      # build + policy refusal
python3 demos/day3_context.py    # compaction, memory, skill
```

### Package map (`odysseus/`)

| File | Role |
|------|------|
| `provider.py` | Only Gemini/HTTP-aware module |
| `loop.py` | model → tools → results → repeat |
| `tools.py` | `@tool` + core file/shell tools (jailed) |
| `security.py` | Policy: read-only / safe / yolo |
| `context.py` | Compaction on `before_turn` |
| `memory.py` | System prompt + `ODYSSEUS.md` |
| `skills.py` | On-demand `skills/<name>/SKILL.md` |
| `session.py` | Durable JSONL sessions |
| `subagent.py` | Depth-limited child agents |
| `harness.py` | Full coding agent assembly |

### Security (coding agent)

`Policy` gates tools. Modes: `read-only`, `safe` (approver), `yolo`. Catastrophic
bash patterns are denied in **every** mode. Blocks become `BLOCKED: ...` tool
results, not crashes.

---

## Chitti mobile harness (without the phone)

CLI against the same API:

```bash
export ODYSSEUS_API_KEY=...
export CHITTI_API_KEY=dev-key-change-me
./scripts/run-server.sh          # terminal 1

export CHITTI_API_KEY=dev-key-change-me
export CHITTI_AUTO_APPROVE=1
python3 demos/mobile_morning_prep.py   # terminal 2
```

Mobile tools (v1): `calendar_list`, `calendar_propose_event`,
`calendar_commit_event` (approval), `draft_message`, `notes_append` (approval),
`remember`, `use_skill`.

---

## Environment variables

| Variable | Used by | Default |
|----------|---------|---------|
| `ODYSSEUS_API_KEY` / `GEMINI_API_KEY` | model | (required for agent turns) |
| `ODYSSEUS_MODEL` | model id | provider default |
| `CHITTI_API_KEY` | phone ↔ server auth | `dev-key-change-me` |
| `CHITTI_HOST` | server bind | `0.0.0.0` |
| `CHITTI_PORT` | server port | `8787` |
| `CHITTI_POLICY` | `read-only` / `safe` / `yolo` | `safe` |

See `.env.example`.

---

## Requirements

| Piece | Need |
|-------|------|
| Coding demos / server | Python 3.10+, network for model API |
| iPhone app | Mac, Xcode 15+, Apple ID, iPhone (iOS 17+) |
| Physical device test | Mac and iPhone on same Wi‑Fi (or USB + LAN access) |

No third-party Python packages for `odysseus/` or `server/` (stdlib HTTP).
