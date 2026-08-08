# Plan: SignalLoop

A **Siri-complemented, iPhone-native agent harness** for **multi-day loops that matter**—**career** and **life**—so ambitious people can break into frontier-shaped work without dropping real-world open loops.

**Product one-liner:**  
> Siri executes requests. SignalLoop pursues objectives—professional and personal—on the phone, with approvals.

**Stack one-liner:**  
> Odysseus-shaped harness organs (loop, tools, policy, memory, skills, session); SignalLoop hands and product model (`Loop` objects). Compute on iPhone except LLM + unavoidable cloud APIs. **No Mac bridge.**

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

**Not** a second Siri. **Not** a Mac remote. **Not** spam auto-DM.

### Coexistence with Siri

| Siri owns | SignalLoop owns |
|-----------|-----------------|
| Language, disambiguation, system reach | Objectives, memory, multi-tool plan |
| Short App Intent turns | Minutes→days state machine |
| Timers, calls, HomeKit, OS privileges | Gmail/GitHub/web tools *you* connect |
| Start / status / approve by voice | Policy, retries, event log, learning |

**Bridge:** [App Intents](https://developer.apple.com/documentation/appintents) — parameters, entities, dialog/snippets. No private “query Siri for all phone data” API.

### What we are *not* building

| Out of scope | Why |
|--------------|-----|
| Compete with Siri OS control | Wrong privilege surface |
| iPhone → Mac / desktop-use node | Explicit product constraint |
| Read all notifications / Messages DB | Not available / not respectable |
| Mass outreach / ungated send | Trust + bans |
| Full paper training on device | Phone is control plane, not GPU cluster |
| General AGI chat app | Sharp loop OS, not chatbot |

### Feature gate

Ship only if someone with **Siri + ChatGPT** still needs SignalLoop:

> Multi-day **state**, **connectors**, **approvals**, and **career+life loops in one graph**.

### Positioning

> Professionals don’t fail only from lack of ambition—they fail from **open loops**.  
> SignalLoop runs the important ones: **break-in work** and **life that must not drop.**

Lead brand with **career systems** (frontier-shaped proof + opportunities). Personal = **capacity & continuity**, not “AI life coach.”

---

## 2. Architecture (locked)

### On-device first; cloud only when unavoidable

```
Siri ──App Intent──► iPhone SignalLoop (source of truth for loops)
                         │
                         ├─ local: state, memory, policy, EventKit, files, Vision
                         ├─ HTTPS ─► LLM API
                         └─ HTTPS ─► Gmail / GitHub / search (user-connected)
```

| On iPhone | Cloud only | Forbidden |
|-----------|------------|-----------|
| Loop state machine, session log | LLM complete | Mac / home agent bridge |
| Memory, skills catalog load | OAuth APIs | OS-wide UI automation |
| Approvals UI, Siri intent handlers | Web fetch/search as tools | Silent send |
| Camera / screenshot intake | — | Notification Center scrape |

**Note on current code:** `server/` is a valid **dev / API-shaped** harness for iteration. Product target remains **orchestration on device** (or on-device with thin API), not “user’s Mac runs the agent.” Revisit server-as-backend only as optional sync—not Mac desktop-use.

### Hybrid server today vs product target

| Phase | Runtime |
|-------|---------|
| **Now (repo)** | Python `server/` + SwiftUI client (fast loop reuse) |
| **Product target** | Loop + Loop store on iPhone; LLM/API from phone; Siri intents on device |
| **Never** | Require Mac node for core value |

### Neutral messages (unchanged)

- `{"role": "user", "text"}`
- `{"role": "assistant", "text", "tool_calls"}`
- `{"role": "tool", "name", "text"}`

Plus product events: `approval_required`, `loop_updated`, `status`.

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
├── drafts[]            # post, email — externalize only after approve
├── links[]             # gmail thread ids, github urls
├── waiting_until
├── outcome             # reply, interview, resolved, abandoned
└── log[]               # user + agent events
```

**Memory (global):** career stack, tone, VIPs, constraints (“no meetings before 10”), household facts that affect both domains.

---

## 4. Siri / App Intents surface (v1)

| Intent | Passes to harness | Result |
|--------|-------------------|--------|
| `NewLoop` | title, domain?, free text | Create loop, optional enqueue plan |
| `Log` | text, optional loop entity | Append evidence/log |
| `Status` | optional loop entity | Short dialog + next blocker |
| `Approve` | draft/action id | Policy gate |
| `Pause` / `Resume` | loop entity | State flip |

**Entities:** `LoopEntity` (query by name/domain/status).

Siri does **not** host multi-day planning; it **starts, interrogates, and gates**.

---

## 5. Tools & skills

### Tools (product target)

| Tool | Side effect | Approval |
|------|-------------|----------|
| `loop_create` / `loop_update` / `loop_get` | local state | no |
| `evidence_add` | local | no |
| `remember` | durable memory | no (user-visible) |
| `web_search` / `fetch_url` | network | no |
| `gmail_search` / `gmail_get_thread` | read | no |
| `gmail_create_draft` | draft | soft / yes |
| `gmail_send` | send | **always** |
| `calendar_propose` / `calendar_commit` | calendar | commit **yes** |
| `draft_post` / `draft_message` | local draft | publish **yes** |
| `use_skill` | load skill text | no |

No `bash`, no desktop click, no Mac spawn.

### Skills (examples)

| Skill | Domain |
|-------|--------|
| `opportunity` | career — research role/lab, map proof gaps |
| `weekly_proof` | career — scope and ship one artifact |
| `outreach_after_proof` | career — draft only post-proof |
| `admin_dispute` | life — bills, claims, landlord |
| `trip_onsite` | both — travel + interview/life logistics |
| `life_admin` | life — letter/photo → deadlines + drafts |

---

## 6. Security & policy

| Mode | Behavior |
|------|----------|
| `read-only` | Search, summarize, propose only |
| `safe` (default) | Drafts free; send/calendar commit need approve |
| `yolo` | Dev only |

Always confirm: send email, public post, delete, money-related actions.

---

## 7. Component map (repo → SignalLoop)

| Repo piece | SignalLoop role |
|------------|-----------------|
| `odysseus/` | Reference coding harness; patterns for loop/policy/session |
| `server/` | Dev harness API; evolve tools toward loops + Gmail |
| `mobile/ios/` | SignalLoop client + App Intents |
| `skills/` | Product skills (`opportunity`, `weekly_proof`, …) |
| `plan.md` | This document |
| `AGENTS.md` | Instructions for coding agents in this repo |

---

## 8. Phased delivery

### Phase 0 — Align
- [x] Product: SignalLoop career + life loops  
- [x] Siri complements; no OS competition  
- [x] On-device orchestration target; no Mac bridge  
- [ ] Rename/brand UI copy toward SignalLoop (incremental)

### Phase 1 — Loop core (server or on-device store)
- [ ] Persist `Loop` objects (JSON/SQLite)  
- [ ] Tools: loop CRUD, evidence, remember  
- [ ] Skills: `opportunity`, `admin_dispute`  
- [ ] Approval on externalize  

### Phase 2 — iOS product shell
- [ ] Loop list + detail cards (not chat-only)  
- [ ] Voice in-app + Siri intents (Log, Status, NewLoop, Approve)  
- [ ] Camera / screenshot share → evidence  

### Phase 3 — Connectors
- [ ] Gmail OAuth: search, get thread, create draft  
- [ ] Calendar propose/commit with approval  
- [ ] Optional GitHub link / later OAuth  

### Phase 4 — Career depth
- [ ] `weekly_proof` skill + artifact checklist  
- [ ] Outreach drafts only after proof gate  
- [ ] Outcome logging (reply / screen / closed)  

### Phase 5 — Polish & launch
- [ ] Privacy copy, data delete, retention  
- [ ] TestFlight  
- [ ] Demo video: career loop + life loop + Siri status  

---

## 9. Success metrics

| Horizon | Signal |
|---------|--------|
| 14 days | User closes or advances ≥1 **career** and ≥1 **life** loop |
| Weekly | ≥1 proof-oriented career step or admin resolution step |
| Virality | Shared **artifacts** or “closed a loop” stories—not referral spam |
| Siri | ≥20% of captures via intents among active users |

---

## 10. Risks

| Risk | Mitigation |
|------|------------|
| Becomes generic chatbot | UI centered on **Loops**, not endless chat |
| Personal dilutes pro brand | Lead career; frame life as capacity |
| Server-only privacy concerns | Move source of truth on-device over time |
| Scope creep (desktop-use, notif scrape) | Explicit non-goals in this plan |
| Hallucinated deadlines/facts | Show evidence quotes; confidence flags |

---

## 11. Immediate next actions

1. Implement `Loop` store + tools against current `server/` *or* iOS-local store (choose one path for v0.1).  
2. Add skills: `opportunity`, `admin_dispute`.  
3. Wire App Intents stubs on iOS: NewLoop, Log, Status, Approve.  
4. Keep Odysseus coding demos intact; don’t break teaching package purity without intent.  
5. Never add Mac-node tools without revising this plan.

---

## 12. North star

**SignalLoop is the persistent, observable, goal-directed harness for career and life open loops—Siri is the universal voice interface that starts, checks, and approves; the iPhone harness is the runtime.**
