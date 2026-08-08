# AGENTS.md — SignalLoop / Chitti repo

Instructions for coding agents (and humans) working in this repository.

---

## What this repo is

| Path | Role |
|------|------|
| `odysseus/` | **Odysseus** — minimal stdlib **coding** agent harness (reference implementation) |
| `server/` | HTTP/SSE mobile harness API (life-ops tools today; evolving toward SignalLoop) |
| `mobile/ios/` | SwiftUI client + Xcode project; Siri/App Intents target surface |
| `skills/` | On-demand `SKILL.md` procedures |
| `demos/` | Runnable teaching demos + mobile API client |
| `plan.md` | **Product + delivery plan** (source of truth for SignalLoop direction) |
| `plan.md` / this file | Update both when product direction changes |

**Product north star: SignalLoop** — an iPhone-native harness for **multi-day loops** (`career` | `life` | `both`), coexisting with **Siri** via App Intents. See `plan.md`.

---

## Non-negotiable product constraints

1. **Do not compete with Siri** for OS control (timers, calls, HomeKit, system settings).  
2. **Siri complements the harness:** capture, status, approve, disambiguate entities — not multi-day planning.  
3. **No Mac / desktop bridge** for core value (no desktop-use node, no “run agent on Mac”).  
4. **Compute on iPhone** for orchestration/state/local tools; **cloud only** for LLM + unavoidable APIs (Gmail, GitHub, search).  
5. **Approve before send / calendar commit / public post** (default `safe` policy).  
6. **No** notification-center scraping, Messages DB access, or Accessibility-based UI automation of other apps.  
7. Prefer **Loop-centric** product work over generic chatbot features.

When unsure, read `plan.md` sections 1–2 and 11.

---

## Architecture rules

### Odysseus (`odysseus/`)

- **Stdlib only** — no third-party packages in this package.  
- Neutral message format only outside `provider.py`.  
- Provider is the sole Gemini/HTTP seam.  
- Loop never crashes on tools; errors become tool results.  
- Keep module docstrings and size/spirit of the teaching build.  
- Do not turn Odysseus into SignalLoop; reuse **patterns**, not product UI.

### Server (`server/`)

- May stay stdlib HTTP for the mobile API.  
- Mobile tools = life-ops / future **loop** tools — **not** coding `bash` jail tools.  
- Approvals: self-gated commits + SSE `approval_required`.  
- Optional path for fast iteration; **product target** is on-device loop ownership (see `plan.md`).  
- Do **not** add Mac-node / desktop click tools.

### iOS (`mobile/ios/`)

- Thin client today; grow **Loop** list/detail, approvals, App Intents.  
- Siri intents (target): `NewLoop`, `Log`, `Status`, `Approve`.  
- Network: LAN/dev server OK; production assumes LLM/API from device or thin backend.  
- Respect Info.plist privacy strings; local networking for debug only.

### Skills

- Files under `skills/<name>/SKILL.md` with optional `description:` line.  
- Prefer SignalLoop skills: `opportunity`, `weekly_proof`, `admin_dispute`, `trip_onsite`, `outreach_after_proof`.

---

## Domain model (implement toward this)

```text
Loop { id, title, domain: career|life|both, status, evidence, steps,
       drafts, links, waiting_until, outcome, log }
```

Global **memory** = durable prefs/facts (career stack, tone, household constraints).

Career and life share **one** harness; do not split into two apps or two incompatible stores.

---

## Coding standards

- Match existing style in the file you edit.  
- Every new module: short docstring (day/concept/rules if Odysseus-style).  
- Public functions: docstrings.  
- Prefer small diffs; no drive-by refactors.  
- Do not commit secrets (`.env`, API keys). Use `.env.example`.  
- Do not commit `server/workspace` runtime junk (memory, sessions, drafts) — gitignored.

---

## Testing expectations

- Prefer smoke tests that need **no** API key (tools, HTTP auth, loop CRUD).  
- Model-calling demos: document required `ODYSSEUS_API_KEY` / `GEMINI_API_KEY`.  
- Mobile: `scripts/run-server.sh` + `scripts/smoke-api.sh` + `demos/mobile_morning_prep.py`.  
- After harness changes: run import/smoke paths that already exist; don’t claim iOS build green on Linux.

---

## What “done” looks like for features

| Feature type | Done means |
|--------------|------------|
| Tool | Schema + run; failure as string; policy/approval if write |
| Loop API | Create/get/update persisted; survives restart |
| Siri intent | Parameters documented; maps to loop action; short dialog result |
| Skill | SKILL.md procedure agents can `use_skill` |
| UI | Loop-visible outcome, not only chat transcript |

---

## Explicitly reject

- “Better Siri” positioning or features that only duplicate system commands  
- Mac SSH/agent bridges as dependencies  
- Auto-send email/social without approval  
- Scraping LinkedIn/personal WhatsApp at scale  
- Expanding scope to general computer-use on device  

---

## Quick commands

```bash
# Coding harness demos
export ODYSSEUS_API_KEY=...
python3 demos/day1_dice.py

# Mobile / SignalLoop-oriented API
export CHITTI_API_KEY=dev-key-change-me
./scripts/run-server.sh
./scripts/smoke-api.sh

# iOS (Mac)
open mobile/ios/Chitti.xcodeproj
```

---

## Documentation ownership

| Doc | Update when |
|-----|-------------|
| `plan.md` | Product intent, architecture locks, phases, non-goals |
| `AGENTS.md` | Agent/developer constraints and repo map |
| `README.md` | Clone/run paths for humans |
| `server/README.md` / `mobile/ios/README.md` | Surface-specific ops |

If product direction changes, **update `plan.md` and `AGENTS.md` in the same change.**
