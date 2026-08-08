# Chitti / Odysseus / SignalLoop

| Piece | What it is |
|-------|------------|
| **Odysseus** | Minimal **coding** agent harness in Python (stdlib only) |
| **Server + iOS shell** | Runnable mobile harness API + SwiftUI client (chat, voice, approvals) |
| **SignalLoop** | **Product north star** — career + life multi-day **loops**; Siri as optional adapter |

An *agent* is a conversation that runs itself: call a model, run tools, feed results back, repeat until the model answers in plain text.

**Continue on a new Mac?** → start here: **[`CONTINUE_ON_MAC.md`](CONTINUE_ON_MAC.md)**  
**Product plan:** [`plan.md`](plan.md) · **Agent rules:** [`AGENTS.md`](AGENTS.md)

---

## Quick start on Mac (clone → server → Xcode → iPhone)

```bash
git clone https://github.com/Raghavan1988/chitti.git
cd chitti

export ODYSSEUS_API_KEY=your_key_here   # or GEMINI_API_KEY
export CHITTI_API_KEY=dev-key-change-me
chmod +x scripts/*.sh
./scripts/run-server.sh                 # leave running; note LAN URL
```

```bash
open mobile/ios/Chitti.xcodeproj
```

1. **Signing & Capabilities** → Apple ID **Team**; unique bundle id if needed.  
2. Run on **Simulator** (`Base URL` `http://127.0.0.1:8787`) or **iPhone** (`http://<mac-lan-ip>:8787`).  
3. App **Settings**: same API key as `CHITTI_API_KEY`.  
4. Trust developer cert on device if prompted.

Details: [`mobile/ios/README.md`](mobile/ios/README.md) · API: [`server/README.md`](server/README.md)

```
iPhone / Simulator  --HTTP/SSE-->  python3 -m server (Mac)  --HTTPS-->  Model API
```

**No Mac-as-agent-node for end users.** The Mac is only your **dev machine** (Xcode + optional local API). See `plan.md`.

---

## SignalLoop (where the product is going)

- **Loops** with domain `career` | `life` | `both` (opportunities, weekly proof, billing disputes, onsite weeks, …).  
- **Siri** = App Intents adapter (NewLoop, LogEvidence, Status, …)—**not** a dependency; full **in-app parity** required.  
- **LoopCommandBus → LoopEngine**; intents do not plan or call tools directly.  
- **iPhone** holds authoritative state; **cloud wake** for schedule/LLM/OAuth/push; **foreground review** before send/post/calendar commit.  
- **No** Notification Center scrape, Messages DB, or desktop-use bridge.

Current iOS app is still a **chat client** to `server/`. Next Mac work: Loop UI + command bus + Siri adapters per `CONTINUE_ON_MAC.md` and `plan.md`.

---

## Layout

```
odysseus/                 coding-agent harness (Python stdlib)
server/                   mobile harness HTTP API + life-ops tools
mobile/ios/
  Chitti.xcodeproj/       open on Mac
  Chitti/                 SwiftUI sources
skills/                   SKILL.md packs
scripts/run-server.sh     API + LAN URL for device
scripts/smoke-api.sh      health check (no model)
demos/                    day1–3 + mobile_morning_prep.py
plan.md                   SignalLoop product + architecture
AGENTS.md                 invariants for coding agents
CONTINUE_ON_MAC.md        handoff checklist for Mac + Xcode
.env.example              env vars
```

---

## Odysseus (coding agent)

Standard library only, Python 3.10+.

```bash
export ODYSSEUS_API_KEY=...   # or GEMINI_API_KEY
python3 demos/day1_dice.py
python3 demos/day2_build.py
python3 demos/day3_context.py
```

Neutral messages: user / assistant(+tool_calls) / tool. Only `provider.py` speaks HTTP/Gemini.

| File | Role |
|------|------|
| `provider.py` | Model HTTP |
| `loop.py` | model → tools → repeat |
| `tools.py` | `@tool` + core file/shell tools |
| `security.py` | Policy |
| `context.py` | Compaction |
| `memory.py` | System prompt + ODYSSEUS.md |
| `skills.py` | On-demand skills |
| `session.py` | JSONL sessions |
| `harness.py` | Full coding agent |

---

## Mobile API without the phone

```bash
export ODYSSEUS_API_KEY=...
export CHITTI_API_KEY=dev-key-change-me
./scripts/run-server.sh

# other terminal
export CHITTI_AUTO_APPROVE=1
python3 demos/mobile_morning_prep.py
```

---

## Environment

| Variable | Purpose | Default |
|----------|---------|---------|
| `ODYSSEUS_API_KEY` / `GEMINI_API_KEY` | Model | required for agent turns |
| `CHITTI_API_KEY` | App ↔ server auth | `dev-key-change-me` |
| `CHITTI_HOST` / `CHITTI_PORT` | Server bind | `0.0.0.0` / `8787` |
| `CHITTI_POLICY` | `read-only` / `safe` / `yolo` | `safe` |

See `.env.example`.

---

## Requirements

| Goal | Need |
|------|------|
| Coding demos / server | Python 3.10+, network for model |
| iPhone / SignalLoop app | **Mac + Xcode 15+**, Apple ID, iPhone optional |
| Physical device | Mac and phone on same Wi‑Fi (or USB + LAN IP) |

Ubuntu/Linux is fine for Python harness work; **iOS build and Siri/App Intents require a Mac.**
