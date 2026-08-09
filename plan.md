# Plan: SignalLoop

A **Siri-complemented, iPhone-native agent harness** for **multi-day loops that matter**—**career** and **life**—so ambitious people can break into frontier-shaped work without dropping real-world open loops.

**Product one-liner:**  
> Siri routes short, user-initiated voice commands. SignalLoop pursues objectives—professional and personal—with durable state, tools, and authenticated review.

**Stack one-liner:**  
> Odysseus-shaped harness organs (loop, tools, policy, memory, skills, session); SignalLoop product model (`Loop` objects) behind a shared **LoopCommandBus**. iPhone holds authoritative state; a **thin cloud wake plane** handles scheduled retrieval, LLM calls, OAuth APIs, and push—not a Mac node.

This repo still contains **Odysseus** (coding harness) and a **mobile server/iOS shell** (`server/`, `mobile/ios/`). SignalLoop is the **product north star** those pieces evolve toward.

---

## 1. Product intent

### What we are building

**SignalLoop** — one app, one primitive:

| Term | Meaning |
|------|---------|
| **Signal** | Something that showed up and matters (role, paper, email, bill, promise, onsite week) |
| **Loop** | Durable multi-day objective: research → act → wait → follow up → done |

Each loop has `domain`: **`career` | `life` | `both`**.

| Career loops | Life loops | Both |
|--------------|------------|------|
| Track lab/role, ship weekly proof | Billing, lease, visa, health admin | Onsite week = interview prep + travel + home logistics |
| Artifact + approved outreach | Dispute drafts + deadlines | Referral coffee + personal story prep |

**Not** a second Siri. **Not** a Mac remote. **Not** spam auto-DM. **Not** Siri-dependent.

### Coexistence with Siri — information boundary

| Siri owns | SignalLoop owns |
|-----------|-----------------|
| User-initiated voice invocation | Objectives, memory, multi-tool plan |
| Transcription and parameter resolution | Minutes→days state machine |
| System routing to App Intents | Gmail/GitHub/web tools *you* connect |
| Short dialog / snippet presentation | Policy, retries, event log, learning |
| Timers, calls, HomeKit, OS privileges | Authoritative loop store and UI |

**What SignalLoop receives from Siri:** only **declared App Intent parameters and entities**—never Siri history, Siri private memory, raw audio retention by Apple as an API, or general phone context.

**What SignalLoop cannot do with Siri:**

- Proactively query Siri  
- Cause Siri to initiate a conversation  
- Treat Siri as a planner, memory store, tool provider, or data source  

**Proactive surfaces (ours):** notifications, widgets, Live Activities, and the **in-app** voice experience—not unsolicited Siri speech.

**Bridge:** modern [App Intents](https://developer.apple.com/documentation/appintents) only (parameters, entities, dialog/snippets). Do not add legacy SiriKit unless a required system domain has no App Intents equivalent.

### Standalone parity (invariant)

> **Every Siri operation must have an equivalent in-app interaction. No core capability, state, or workflow may require Siri.**

SignalLoop must remain fully usable if the user never enables Siri, never grants voice, or only uses chat/camera/share.

### What we are *not* building

| Out of scope | Why |
|--------------|-----|
| Compete with Siri OS control | Wrong privilege surface |
| Siri as information source or planner | Not exposed; weakens product boundary |
| Siri-only workflows | Violates standalone parity |
| iPhone → Mac / desktop-use node | Explicit product constraint |
| Read all notifications / Messages DB | Not available / not respectable |
| Mass outreach / ungated send | Trust + bans |
| Silent externalize from background/cloud | Safety |
| Full paper training on device | Phone is control plane, not GPU cluster |
| General AGI chat app | Sharp loop OS, not chatbot |

### Feature gate

Ship only if someone with **Siri + ChatGPT** still needs SignalLoop **and** the feature works **without Siri**:

> Multi-day **state**, **connectors**, **review gates**, and **career+life loops in one graph**—with full in-app parity for every voice command.

### Positioning

> Professionals don’t fail only from lack of ambition—they fail from **open loops**.  
> SignalLoop runs the important ones: **break-in work** and **life that must not drop.**

Lead brand with **career systems** (frontier-shaped proof + opportunities). Personal = **capacity & continuity**, not “AI life coach.”

---

## 2. Architecture (locked)

### Adapter architecture — one command bus

Siri must **not** call the planner or tools directly. Every surface submits **commands** to the same bus.

```text
SwiftUI / Siri / Share Extension / Widget / Notifications
                        │
                  LoopCommandBus
              (source + idempotency key)
                        │
                    LoopEngine
            memory · policy · tools · log
                        │
          ┌─────────────┼─────────────┐
          ▼             ▼             ▼
     local tools    LLM API     OAuth / fetch
     (EventKit…)   (cloud)     (cloud wake OK)
```

| Rule | Detail |
|------|--------|
| Adapters | Siri App Intent handlers only **translate** → `LoopCommand` |
| No Siri-specific business logic | Planning, memory writes, tool choice live in **LoopEngine** only |
| Idempotency | Every command carries `source` + `idempotency_key`; repeats must not duplicate loops, evidence, or actions |
| Core isolation | Core harness modules **must not import AppIntents** |

### Runtime split: device authority + cloud wake plane

iOS background scheduling is **opportunistic and system-controlled**; do not assume exact-time multi-day monitoring on-device alone ([Apple background guidance](https://developer.apple.com/documentation/backgroundtasks/choosing-background-strategies-for-your-app)).

| Plane | Owns |
|-------|------|
| **iPhone** | Authoritative loop state, private memory, approvals UI, local tools, command bus, review for consequential actions |
| **Cloud wake plane** | Scheduled retrieval, LLM calls, OAuth API pulls, push delivery when something needs attention |
| **Forbidden** | Mac node; cloud **silent** send/post/calendar-commit/delete/spend |

**Consequential side effects** (email send, public post, calendar commit, delete, financial) require an **approval / review token** established in an **authenticated foreground** SignalLoop review—not a free-form Siri “approve everything.”

```
User / Siri / Share ──command──► iPhone LoopEngine (source of truth)
                                      │
                                      ├─ local tools
                                      ├─ enqueue research / fetch jobs
                                      ▼
                               Cloud wake plane
                               (LLM, Gmail read, search, push)
                                      │
                                      ▼
                               Device: draft ready / needs review
```

### Repo phases vs product target

| Phase | Runtime |
|-------|---------|
| **Now (repo)** | Python `server/` + SwiftUI client (iteration) |
| **Product target** | LoopEngine + store on iPhone; cloud wake for schedule/LLM/OAuth/push |
| **Never** | Mac node; Siri as dependency for core paths |

### Neutral messages (agent transcript)

- `{"role": "user", "text"}`
- `{"role": "assistant", "text", "tool_calls"}`
- `{"role": "tool", "name", "text"}`

Plus product events: `review_required`, `loop_updated`, `status`, `job_complete`.

---

## 3. Data model (core)

```text
Loop
├── id, title
├── domain: career | life | both
├── status: active | waiting | blocked | done
├── why_it_matters
├── evidence[]          # notes, URLs, photos, screenshots, voice transcripts
├── steps[] / blockers[] / next_action
├── drafts[]            # post, email — externalize only after foreground review
├── links[]             # gmail thread ids, github urls
├── waiting_until
├── outcome             # reply, interview, resolved, abandoned
└── log[]               # user + agent events (include command source)

LoopCommand
├── type, payload
├── source: siri | app | share | widget | notification | cloud_wake
└── idempotency_key
```

**Memory (global):** career stack, tone, VIPs, constraints (“no meetings before 10”), household facts that affect both domains. **Not** Siri memory.

---

## 4. Siri / App Intents surface (v1)

Prefer **narrow, reversible** voice actions. Consequential externalization uses **Review**, not a general Approve.

| Intent | Siri behavior |
|--------|----------------|
| `NewLoop` | Create a loop (params: title, domain?, text) |
| `LogEvidence` | Append text or evidence pointer to a loop |
| `Status` | Return **privacy-safe** status (lock-screen safe projection) |
| `Pause` / `Resume` | Change loop state |
| `ApprovePlan` | Approve an **internal, reversible** plan (next steps checklist)—not send/post |
| `ReviewAction` | Open **authenticated in-app** review for a pending external action |
| `MarkComplete` | Record **user-reported** completion |

**Entities:** `LoopEntity` (query by name/domain/status).

**Must stay in-app (visual review), not Siri-complete:**

- Email **send**  
- Public **post**  
- **Calendar commit**  
- **Delete**  
- **Financial** actions  

**Status privacy:** when locked / glanceable, never speak email bodies, recipient details, health content, or sensitive life-loop evidence. Use redacted projections (“1 career loop waiting on reply”).

**In-app parity:** each intent above has a first-class UI action (create loop, log, status board, pause/resume, approve plan, open review sheet, mark complete).

---

## 5. Tools & skills

### Tools (product target)

| Tool | Side effect | Gate |
|------|-------------|------|
| `loop_create` / `loop_update` / `loop_get` | local state | none |
| `evidence_add` | local | none |
| `remember` | durable memory | user-visible |
| `web_search` / `fetch_url` | network | none (draft-level) |
| `gmail_search` / `gmail_get_thread` | read | none |
| `gmail_create_draft` | draft in mailbox | soft / review |
| `gmail_send` | send | **foreground review** |
| `calendar_propose` / `calendar_commit` | calendar | commit = **foreground review** |
| `draft_post` / `draft_message` | local draft | publish = **foreground review** |
| `use_skill` | load skill text | none |

Background/cloud jobs may **research, fetch, draft, notify**—not silently externalize.

No `bash`, no desktop click, no Mac spawn.

### Skills (examples)

| Skill | Domain |
|-------|--------|
| `opportunity` | career — research role/lab, map proof gaps |
| `weekly_proof` | career — scope and ship one artifact |
| `outreach_after_proof` | career — draft only post-proof |
| `trip_onsite` | both — travel + interview/life logistics |
| `life_admin` | life — letter/photo → deadlines + drafts |

---

## 6. Security & policy

| Mode | Behavior |
|------|----------|
| `read-only` | Search, summarize, propose only |
| `safe` (default) | Drafts OK; externalize via authenticated foreground review |
| `yolo` | Dev only |

| Allowed via Siri (local/reversible) | Requires in-app review |
|-------------------------------------|-------------------------|
| NewLoop, LogEvidence, Status, Pause/Resume | gmail_send, publish post |
| ApprovePlan (internal checklist) | calendar_commit, delete |
| MarkComplete (user-reported) | spend / money-related |
| ReviewAction → opens app | — |

---

## 7. Component map (repo → SignalLoop)

| Repo piece | SignalLoop role |
|------------|-----------------|
| `odysseus/` | Reference coding harness; patterns for loop/policy/session |
| `server/` | Dev harness + future **cloud wake** sketch (not Mac node) |
| `mobile/ios/` | LoopEngine host candidate, UI, App Intent **adapters** |
| `skills/` | Product skills |
| `plan.md` | This document |
| `AGENTS.md` | Implementation invariants for coding agents |
| `CONTINUE_ON_MAC.md` | Mac + Xcode handoff |

---

## 8. Phased delivery

### Phase 0 — Align
- [x] Product: SignalLoop career + life loops  
- [x] Siri adapter boundary + standalone parity  
- [x] Command bus + cloud wake plane; no Mac bridge  
- [x] Mac handoff docs (`CONTINUE_ON_MAC.md`, README, shared Xcode scheme)  
- [ ] Rename/brand UI copy toward SignalLoop (incremental)

### Phase 1 — Loop core + command bus
- [x] Persist `Loop` + `LoopCommand` (idempotent)  
- [x] LoopEngine + tools: loop CRUD, evidence, remember  
- [x] Skills: `opportunity`  
- [x] In-app review sheet for externalize  

### Phase 2 — Multi-surface adapters (parity first)
- [x] SwiftUI: loop list/detail, log, status, review  
- [x] App Intents: NewLoop, LogEvidence, Status, Pause/Resume, ApprovePlan, ReviewAction, MarkComplete  
- [x] Share + camera → LogEvidence-equivalent command  
- [x] **Prove every intent has UI twin**  

### Phase 3 — Cloud wake plane
- [ ] Scheduled/retrieval jobs (Gmail read, web, LLM plan/draft)  
- [ ] Push when draft/review ready  
- [ ] No silent send from cloud  

### Phase 4 — Career depth
- [ ] `weekly_proof` + proof gate before outreach drafts  
- [ ] Outcome logging  

### Phase 5 — Polish & launch
- [ ] Privacy projections for Status  
- [ ] Data delete / retention  
- [ ] TestFlight + demo: career loop + life loop + Siri status **and** pure in-app path  

---

## 9. Success metrics

| Horizon | Signal |
|---------|--------|
| 14 days | User advances ≥1 **career** and ≥1 **life** loop **without requiring Siri** |
| Weekly | ≥1 proof-oriented career step or admin resolution step |
| Virality | Shared **artifacts** or “closed a loop” stories—not referral spam |
| Siri | Optional convenience: share of captures via intents; **not** a funnel requirement |
| Safety | Zero silent externalize from background/cloud in production |

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| Treat Siri as data source | Intent params only; documented boundary |
| Planning inside intents | Command bus + LoopEngine only |
| Unsafe voice “approve send” | ReviewAction + foreground review |
| Assume continuous iOS background | Cloud wake plane |
| Siri-only features | Standalone parity gate |
| Generic chatbot | UI centered on **Loops** |
| Personal dilutes pro brand | Lead career; life = capacity |
| Hallucinated facts | Evidence quotes; confidence flags |

---

## 11. Immediate next actions

**On Mac (see `CONTINUE_ON_MAC.md`):**

1. Clone, `./scripts/run-server.sh`, open `mobile/ios/Chitti.xcodeproj`, run Simulator.  
2. Define `LoopCommand` schema + idempotency in store (server and/or iOS).  
3. Implement LoopEngine operations behind the bus (no AppIntents imports in core).  
4. In-app UI for all v1 commands **before** or **with** Siri adapters.  
5. Skills: `opportunity`.  
6. Never add Mac-node tools or Siri-only core workflows without revising this plan.

---

## 12. North star

**SignalLoop is the persistent, observable, goal-directed harness for career and life open loops. Siri is an optional voice adapter into the same command bus—not a dependency, not a data source, not a planner. The iPhone holds truth; the cloud wakes research and delivery; consequential actions wait for authenticated in-app review.**
