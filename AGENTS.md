# AGENTS.md — SignalLoop / Chitti repo

Instructions for coding agents (and humans) working in this repository.

---

## What this repo is

| Path | Role |
|------|------|
| `odysseus/` | **Odysseus** — minimal stdlib **coding** agent harness (reference implementation) |
| `server/` | HTTP/SSE mobile harness API; evolving toward LoopEngine + cloud wake plane |
| `mobile/ios/` | SwiftUI surfaces + App Intent **adapters** (not planners) |
| `skills/` | On-demand `SKILL.md` procedures |
| `demos/` | Runnable teaching demos + mobile API client |
| `plan.md` | **Product + architecture** (source of truth) |
| `AGENTS.md` | **Implementation invariants** for agents (this file) |
| `CONTINUE_ON_MAC.md` | Handoff for Mac + Xcode development |

**Product north star: SignalLoop** — multi-day loops (`career` | `life` | `both`), Siri as **optional adapter**, on-device authoritative state, thin cloud wake plane, **no Mac bridge**. See `plan.md`.

---

## SignalLoop product invariants

### Standalone product

- SignalLoop must remain **fully usable without Siri**.  
- Every App Intent must have an **equivalent in-app operation**.  
- No core workflow may depend on a Mac, desktop node, or Siri availability.  
- Do not ship Siri-only features that weaken the standalone product.

### Siri boundary

- Use **modern App Intents**; do not add legacy SiriKit unless a required system domain has no App Intents equivalent.  
- **Siri is an adapter**, not a planner, memory store, tool provider, or data source.  
- Never assume access to Siri history, raw audio as an API, general personal context, Notification Center, Messages, or arbitrary phone data.  
- SignalLoop receives only **explicitly declared** App Intent parameters and entities.  
- SignalLoop **cannot proactively query Siri** or initiate a Siri conversation.  
- Proactive UX uses **notifications, widgets, Live Activities, and in-app voice**—not unsolicited Siri dialog.

### Architecture

- Core harness / LoopEngine modules **must not import AppIntents**.  
- App Intent handlers **only translate** requests into **LoopCommandBus** commands.  
- **Siri-specific business logic is prohibited** (no planning or policy forks “if source == siri” except privacy projection / UX).  
- All commands must carry **`source`** and **`idempotency_key`**.  
- Repeated Siri (or any) invocations must **not duplicate** loops, evidence, or actions.  
- Surfaces (SwiftUI, Siri, Share, Widget, notification actions) → **LoopCommandBus** → **LoopEngine** (memory · policy · tools · log).

### Safety

- Siri may execute **local, reversible** operations (create loop, log evidence, status, pause/resume, approve **internal** plan, mark complete, open review).  
- **Sending, publishing, deleting, spending, or committing calendar changes** requires **authenticated foreground review** in SignalLoop—not a general voice “Approve.”  
- Prefer intents: `NewLoop`, `LogEvidence`, `Status`, `Pause`/`Resume`, `ApprovePlan`, `ReviewAction`, `MarkComplete` (see `plan.md`).  
- Siri **Status** must use a **privacy-safe projection** when locked; never speak email contents, recipient details, health information, or sensitive life-loop evidence from the lock screen.  
- Default policy is **safe**: drafts OK; externalize only after review.

### Background execution

- Do **not** assume `BGTaskScheduler` (or similar) runs at an exact time or cadence.  
- Reliable multi-day monitoring uses the approved **cloud wake plane** (scheduled retrieval, LLM, OAuth reads, push).  
- Background and cloud jobs may **research, fetch, draft, or notify**; they may **not** silently externalize an action.  
- Cloud must not perform consequential side effects without an **approval/review token** from foreground review.  
- **No Mac / desktop node** for core value.

---

## Non-negotiable product constraints (summary)

1. Do not compete with Siri for OS control (timers, calls, HomeKit, settings).  
2. Siri complements via App Intents adapters only—not multi-day planning.  
3. No Mac / desktop bridge.  
4. iPhone: authoritative loops + memory + review UI; cloud: wake + LLM + OAuth APIs + push.  
5. Loop-centric product—not generic chatbot.  
6. No notification scraping, Messages DB, or Accessibility UI automation of other apps.  

When unsure, read `plan.md` sections 1–2, 4, and 11.

---

## Architecture rules by package

### Odysseus (`odysseus/`)

- **Stdlib only** — no third-party packages.  
- Neutral message format only outside `provider.py`.  
- Provider is the sole Gemini/HTTP seam.  
- Loop never crashes on tools; errors become tool results.  
- Do not turn Odysseus into SignalLoop; reuse **patterns**, not product UI.  
- Must not gain AppIntents or Siri dependencies.

### Server (`server/`)

- Stdlib HTTP OK for dev API / future cloud wake sketch.  
- Loop tools — **not** coding `bash` jail tools.  
- Approvals: no silent externalize; review tokens for send/commit.  
- Do **not** add Mac-node / desktop click tools.  
- Prefer command-shaped APIs (idempotent) as LoopCommandBus evolves.

### iOS (`mobile/ios/`)

- Grow Loop list/detail, in-app review, command bus host.  
- App Intent handlers: **thin adapters** → LoopCommandBus only.  
- Target intents: `NewLoop`, `LogEvidence`, `Status`, `Pause`/`Resume`, `ApprovePlan`, `ReviewAction`, `MarkComplete`.  
- Implement **in-app twins** for every intent before treating Siri as done.  
- Core engine code: no `import AppIntents`.

### Skills

- `skills/<name>/SKILL.md` with optional `description:` line.  
- Prefer: `opportunity`, `weekly_proof`, `trip_onsite`, `outreach_after_proof`.

---

## Domain model (implement toward this)

```text
Loop { id, title, domain: career|life|both, status, evidence, steps,
       drafts, links, waiting_until, outcome, log }

LoopCommand { type, payload, source, idempotency_key }
```

Global **memory** = durable prefs/facts (not Siri memory).  
Career and life share **one** store and engine.

---

## Coding standards

- Match existing style in the file you edit.  
- Public functions: docstrings; Odysseus modules keep teaching docstrings.  
- Prefer small diffs; no drive-by refactors.  
- Do not commit secrets (`.env`, API keys).  
- Do not commit `server/workspace` runtime junk — gitignored.

---

## Testing expectations

- Smoke tests without API keys where possible (tools, auth, loop CRUD, command idempotency).  
- Model demos: document `ODYSSEUS_API_KEY` / `GEMINI_API_KEY`.  
- Mobile: `scripts/run-server.sh`, `scripts/smoke-api.sh`, `demos/mobile_morning_prep.py`.  
- For Siri work: assert **in-app parity** and that core packages do not import AppIntents.  
- Do not claim iOS build green on Linux.

---

## What “done” looks like for features

| Feature type | Done means |
|--------------|------------|
| Tool | Schema + run; failure as string; review if externalize |
| Loop API | Persist; survive restart; command-idempotent writes |
| App Intent | Thin adapter; **in-app twin**; short privacy-safe dialog |
| Skill | SKILL.md loadable via `use_skill` |
| UI | Loop-visible outcome, not chat-only |
| Cloud job | May draft/notify; cannot silent-send |

---

## Explicitly reject

- Treating Siri as an information source or planner  
- Planning or tool execution **inside** intent handlers  
- General Siri `Approve` that sends/posts/commits  
- Siri-only core workflows  
- Mac SSH/agent bridges as dependencies  
- Assuming reliable exact-time iOS background monitoring alone  
- Silent externalize from background or cloud  
- Scraping LinkedIn/personal WhatsApp at scale  
- Notification Center / Messages graph access  
- “Better Siri” positioning  

---

## Continuing on Mac + Xcode

Primary handoff doc: **`CONTINUE_ON_MAC.md`** (clone → server → Xcode → device → next work).

- iOS build / Siri / App Intents **require a Mac**; Linux is fine for `odysseus/` + `server/` only.
- On Mac, implement **in-app Loop UI and command bus before** relying on Siri.
- Do not treat the developer Mac as a product “desktop agent node.”

## Quick commands

```bash
export ODYSSEUS_API_KEY=...
python3 demos/day1_dice.py

export CHITTI_API_KEY=dev-key-change-me
./scripts/run-server.sh
./scripts/smoke-api.sh

# Mac
open mobile/ios/Chitti.xcodeproj
# full checklist: CONTINUE_ON_MAC.md
```

---

## Documentation ownership

| Doc | Update when |
|-----|-------------|
| `plan.md` | Product intent, architecture locks, phases, non-goals |
| `AGENTS.md` | Implementation invariants (this file) |
| `CONTINUE_ON_MAC.md` | Mac clone/Xcode checklist and “what next” |
| `README.md` | Clone/run for humans |
| `server/README.md` / `mobile/ios/README.md` | Surface ops |

If product direction changes, **update `plan.md` and `AGENTS.md` in the same change.**
