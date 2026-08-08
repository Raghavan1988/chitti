# Plan: iPhone Harness (Chitti Mobile)

A plan to build an **agent harness for iPhone** — voice + chat — that does tasks **Siri is weak at**: multi-step work across *your* services, with judgment, durable memory, and confirm-before-write policy.

This plan reuses the mental model of **Odysseus** (`odysseus/` in this repo): provider, loop, tools, policy, context, memory, skills, session, subagent, harness. The hands change; the organs stay the same.

---

## 1. Product intent

### What we are building

An iPhone app that is a **personal ops agent**:

- **Chat** and **push-to-talk voice** as the UI (not always-on “Hey …” — that is Siri’s surface).
- A real **agent loop**: model → tools → results → repeat until a final answer.
- **Tools** into systems Siri does not run well (or at all) for *your* stack: email drafts, calendar planning with constraints, notes, web research, custom APIs, optional desktop/home Odysseus.
- **Policy**: read freely; writes as drafts; irreversible actions need explicit user approval.
- **Memory + sessions**: facts and conversations survive restarts.

### What we are *not* building

| Out of scope (v1–v2) | Why |
|----------------------|-----|
| Replacing Siri for timers / calls / HomeKit | Siri has OS privilege; we lose |
| Always-on wake word | Platform + battery + App Store |
| Unrestricted UI automation of arbitrary apps | Not App Store–viable |
| Full on-device coding agent (`bash` / free filesystem) | iOS sandbox; different product (keep Odysseus on Mac/server) |
| “General AGI phone” | Focus on a sharp job-to-be-done |

### Siri test (feature gate)

Ship a feature only if a user who already has Siri + ChatGPT would still open this app:

> Multi-step + connected accounts + memory + approval beats a one-shot OS command.

### v1 job-to-be-done (locked for plan)

**Morning / day prep agent** for one person (you first):

> “Look at my next 48 hours and open loops; propose a plan; draft messages and calendar changes; execute only what I approve.”

Later verticals (work ops, expenses, trip planner) reuse the same harness with new tools/skills.

---

## 2. Architecture decision

### Chosen shape: hybrid harness

```
┌──────────────────────────────────────────────┐
│  iPhone (SwiftUI)                            │
│  • Chat + push-to-talk                       │
│  • Plan / approval cards                     │
│  • Local session cache + keychain tokens     │
│  • App Intents / Shortcuts entry (“ask …”)   │
└────────────────────┬─────────────────────────┘
                     │ HTTPS (SSE or WebSocket)
                     ▼
┌──────────────────────────────────────────────┐
│  Harness server (Python — Odysseus-shaped)   │
│  • loop, policy, context, memory, skills     │
│  • tool registry (OAuth services + iOS-safe) │
│  • session JSONL / DB                        │
└────────────────────┬─────────────────────────┘
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       LLM API   External APIs  Optional desktop
                 (Gmail, Cal…)  Odysseus node
```

**Why hybrid first**

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| Brain on server (hybrid) | Reuse Odysseus; fast iteration; strong models; heavy tools off-phone | You host user data; need auth | **v1** |
| Loop on phone, model cloud | More on-device control | Duplicates harness in Swift; harder tools | v2 option |
| Fully on-device | Max privacy / offline | Weak general agent; tool limits | niche later |

**Design rule:** the iPhone is a **rich client** for I/O, approvals, and local sensors; the **harness** remains the source of truth for the agent loop (same as Odysseus).

### Neutral message format (keep compatible with Odysseus)

- `{"role": "user", "text"}`
- `{"role": "assistant", "text", "tool_calls"}`
- `{"role": "tool", "name", "text"}`

Plus mobile-only **UI events** over the wire (not model-facing):

- `plan` — proposed steps before side effects  
- `approval_required` — tool gated until user confirms  
- `status` — tool_start / tool_end for the transcript UI  

---

## 3. Component map (Odysseus → iPhone harness)

| Odysseus | Mobile harness role |
|----------|---------------------|
| `provider.py` | LLM client on server (reuse / swap model) |
| `loop.py` | Same loop; stream events to phone |
| `tools.py` | New tool set (no bash jail; service tools) |
| `security.py` | Policy modes + **approval channel** to phone |
| `context.py` | Compaction on long day-long chats |
| `memory.py` | User profile + project memory (`MEMORY.md` or DB) |
| `skills.py` | `skills/<name>/SKILL.md` (morning_prep, etc.) |
| `session.py` | Durable sessions; phone can resume by id |
| `subagent.py` | Optional later (research child, calendar child) |
| `harness.py` | Server `Harness` + HTTP API |
| *(new)* iOS app | Chat, voice STT/TTS, approval UI, App Intents |
| *(new)* auth | User accounts + OAuth for tools |
| *(new)* gateway | REST + streaming for the phone |

---

## 4. Repository layout (target)

Evolve this repo (or split later if needed):

```
chitti/
  odysseus/                 # existing desktop/CLI harness (keep)
  plan.md                   # this file
  mobile/
    ios/                    # SwiftUI app (Xcode project)
      App/
      Features/
        Chat/
        Voice/
        Approvals/
        Settings/
      Services/             # API client, keychain, STT/TTS
  server/
    api/                    # FastAPI (or similar) over harness
    tools/                  # mobile-oriented tools
    auth/                   # session + OAuth token store
  skills/
    morning_prep/SKILL.md
  demos/                    # keep existing; add API demos later
```

**Constraint preference:** reuse `odysseus` packages for loop/provider/context/session where possible; add a thin `server/` layer rather than rewriting the agent brain in Swift for v1.

**Note:** Odysseus is currently stdlib-only. The mobile *server* may add minimal deps (e.g. FastAPI, httpx) **only in `server/`**, leaving `odysseus/` pure if we want to keep the teaching package clean. Decision: **server may depend on packages; odysseus stays stdlib unless we deliberately merge.**

---

## 5. Security & policy (product, not afterthought)

### Modes

| Mode | Behavior |
|------|----------|
| `read-only` | Calendar/mail/notes **read**; no create/update/send |
| `safe` (default) | Writes produce **drafts** or require **Approve** on device |
| `yolo` | Auto-run allowed tools (dev only; not default in App Store build) |

### Always-confirm classes

- Send email / message  
- Create or modify calendar events  
- Delete anything  
- Spend money / transfer  
- Post to shared channels (Slack, etc.)  

Blocked or pending tools return structured results the model can work around (`BLOCKED: …` / `PENDING_APPROVAL: …`), never crash the loop — same Odysseus rule.

### Privacy

- Tokens in Keychain on device; server stores refresh tokens encrypted at rest.  
- Clear data export/delete path before any public release.  
- Do not request contacts/mic/calendar until the feature needs them (purpose strings ready).

---

## 6. v1 toolbelt (small, high leverage)

Start with **≤ 8 tools**. Every tool must pass the Siri test.

| Tool | Side effect | Approval |
|------|-------------|----------|
| `calendar_list` | none | no |
| `calendar_propose_event` | none (returns draft JSON) | n/a |
| `calendar_commit_event` | creates event | **yes** |
| `notes_append` | writes note | safe: yes / optional |
| `remember` | durable memory | no (user-visible in settings) |
| `recall` / memory is in system prompt | none | no |
| `web_search` or `fetch_url` | none | no |
| `draft_message` | stores draft for user to send | no auto-send in v1 |
| `use_skill` | loads skill text | no |

**Explicitly deferred:** Gmail/Slack OAuth (v1.1), WhatsApp (platform limits), desktop `spawn_odysseus` (v2), payments.

**iOS-local tools (optional later, on-device):** EventKit write after server proposes; can be “server proposes → phone commits via EventKit” to reduce server holding calendar write scope.

### Preferred commit path for calendar (recommended)

1. Server tool: read calendar via OAuth **or** phone uploads next-48h snapshot.  
2. Model proposes events as structured drafts.  
3. Phone shows approval card → commits via **EventKit** on device.  

That keeps write privilege closer to the user and simplifies App Store narrative.

---

## 7. iOS client scope

### Screens (v1)

1. **Chat** — transcript (user / assistant / tool status / drafts)  
2. **Voice** — hold-to-talk → STT → same send path as chat; TTS for final answer (optional toggle)  
3. **Approvals** — inline cards: Approve / Edit / Reject  
4. **Settings** — API endpoint, model, policy mode, memory viewer, linked accounts  
5. **Onboarding** — mic permission, what the agent can/can’t do, connect calendar  

### Platform hooks

- **Speech:** `SFSpeechRecognizer` (or cloud STT if quality demands)  
- **Speech out:** `AVSpeechSynthesizer` first; nicer TTS later  
- **App Intents / Shortcuts:** “Ask Chitti” with text parameter → opens session  
- **Share sheet (v1.1):** share PDF/text into a new task  

### Non-goals for client

- Implementing the full tool loop in Swift in v1  
- Background always-listening  
- Local LLM required for v1  

---

## 8. Server API (sketch)

Auth: bearer token per user (API key for solo dev; proper auth before multi-user).

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/v1/sessions` | Create session |
| `GET` | `/v1/sessions/{id}` | Load messages |
| `POST` | `/v1/sessions/{id}/messages` | User text; starts/continues loop |
| `GET` | `/v1/sessions/{id}/events` | SSE stream: assistant tokens, tool_*, approval_* |
| `POST` | `/v1/sessions/{id}/approvals/{aid}` | approve / reject |
| `GET` | `/v1/memory` | Read durable memory |
| `PUT` | `/v1/memory` | User-edited memory |

Loop behavior on each user message: same as `Harness.run`, but stream `on_event` to SSE; pause on tools that need approval until the approvals endpoint resolves (or timeout → `BLOCKED`).

---

## 9. Phased delivery

### Phase 0 — Spec freeze (0.5 day)

- [x] Product intent + hybrid architecture (this doc)  
- [ ] Confirm v1 tools list and approval matrix  
- [ ] Confirm solo-dev auth: single API key vs Apple Sign In later  
- [ ] Choose server stack: FastAPI + reuse `odysseus` (recommended)  

### Phase 1 — Server harness slice (Days 1–2)

**Goal:** HTTP-driven Odysseus-shaped agent with mobile-safe tools and mock approvals.

- [ ] `server/` package: app entry, config from env  
- [ ] Wire existing `run_loop` / `Harness` patterns behind `POST .../messages`  
- [ ] SSE event bridge from `on_event`  
- [ ] Tools: `remember`, `calendar_list` (fixture or ICS fixture first), `draft_message`, `use_skill`  
- [ ] Policy: `safe` blocks commit tools without approval id  
- [ ] Skill: `skills/morning_prep/SKILL.md`  
- [ ] Demo script: `demos/mobile_morning_prep.py` (CLI client against API)  
- [ ] Session persistence (reuse `session.py` or DB)  

**Exit criteria:** curl/SSE session completes a multi-tool morning-prep style task with one approval pause.

### Phase 2 — iOS thin client (Days 3–5)

**Goal:** Chat app that talks to the server end-to-end.

- [ ] Xcode project under `mobile/ios`  
- [ ] Auth: paste API base URL + key into Keychain  
- [ ] Chat UI + streaming transcript  
- [ ] Render tool_start/tool_end as compact rows  
- [ ] Approval cards wired to approvals API  
- [ ] Settings screen  
- [ ] Error states (offline, 401, loop error)  

**Exit criteria:** From a real iPhone/Simulator, run a full morning-prep conversation with one approve/reject.

### Phase 3 — Voice (Day 6)

- [ ] Push-to-talk → STT → send as user message  
- [ ] Optional TTS on final assistant text  
- [ ] Mic permission copy + graceful denial  

**Exit criteria:** Hands-free ask → plan → approve on screen → spoken summary.

### Phase 4 — Real calendar path (Days 7–8)

- [ ] Choose: Google Calendar OAuth on server **or** EventKit snapshot + on-device commit  
- [ ] Implement list + propose + commit with approval  
- [ ] Timezone correctness tests  
- [ ] Memory: preferences (“no meetings before 10”)  

**Exit criteria:** Agent proposes a real event; user approves; it appears in Calendar.

### Phase 5 — Siri as doorbell (Day 9)

- [ ] App Intent: `AskChittiIntent(text:)`  
- [ ] Shortcuts phrase documentation  
- [ ] Deep link into the right session  

**Exit criteria:** “Hey Siri, ask Chitti what’s on my plate tomorrow” opens/runs the agent path (Siri launches; Chitti reasons).

### Phase 6 — Harden for daily use (Days 10–12)

- [ ] Compaction on long sessions (`context.compact`)  
- [ ] Crash-safe resume (session load on app launch)  
- [ ] Rate limits + basic abuse controls on API  
- [ ] Logging without leaking message bodies in prod  
- [ ] Privacy policy stub + data delete  
- [ ] TestFlight checklist  

**Exit criteria:** You use it for 3 real mornings without the developer console.

### Later (explicit backlog)

- Gmail draft/send-with-approval  
- Slack / Linear  
- Share sheet → PDF skill  
- Subagents  
- On-device loop option  
- Desktop Odysseus tool (`run_on_mac`)  
- Multi-user accounts + Apple Sign In  

---

## 10. Mapping to “days” (teaching + build order)

Mirror Odysseus pedagogy so the mobile harness stays understandable:

| Day | Deliverable |
|-----|-------------|
| M1 | Server loop + SSE + one tool (`remember`) |
| M2 | Policy + approval protocol + `draft_message` |
| M3 | Skills + memory in system prompt + morning_prep |
| M4 | Sessions + resume API |
| M5 | iOS chat client |
| M6 | Voice I/O |
| M7 | Calendar propose/commit |
| M8 | App Intents + polish |

---

## 11. Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Competing with Siri AI improvements | Stay on *your* tools + policy + memory; use Siri only as launcher |
| App Store rejection (automation / spam) | No UI scraping; user-initiated actions; clear approvals |
| OAuth / token security | Keychain; encrypted server store; short-lived access tokens |
| Latency on voice | Stream partial assistant text; TTS only final summary |
| Scope creep (too many integrations) | Hard cap: morning prep + calendar until daily use works |
| Odysseus stdlib purity vs server deps | Isolate deps in `server/`; don’t pollute teaching package |

---

## 12. Success metrics

**v1 success (personal):**

1. You complete a real morning prep **by voice or chat** without opening Calendar/Mail first.  
2. At least one **write** goes through an **approval card** (not silent side effect).  
3. A preference stored via `remember` affects a **later** session.  
4. A session survives app kill and resumes.  
5. Siri/Shortcuts can **start** a Chitti task (optional but targeted in Phase 5).

**Non-metrics (ignore early):** DAU, App Store ranking, parity with Siri system commands.

---

## 13. Open decisions (resolve in Phase 0)

| Decision | Options | Recommendation |
|----------|---------|----------------|
| Server framework | stdlib HTTP vs FastAPI | FastAPI in `server/` for SSE ergonomics |
| Calendar authority | Google OAuth vs EventKit-on-device | EventKit commit on device for v1 |
| LLM | Keep Gemini via Odysseus provider vs multi-provider | Keep current provider; abstract already exists |
| Auth | Static API key vs Sign in with Apple | API key until TestFlight multi-user |
| Repo | Monorepo vs `chitti-ios` split | Monorepo until app ships TestFlight |
| Product name | Chitti / Odysseus Mobile / other | **Chitti** for app; Odysseus for brain package |

---

## 14. Immediate next actions

When implementation starts (after this plan is accepted):

1. Create `server/` skeleton + env sample (`ODYSSEUS_API_KEY`, `CHITTI_API_KEY`, `PORT`).  
2. Expose `Harness.run` over one streaming endpoint with `remember` + stub calendar.  
3. Add `skills/morning_prep/SKILL.md`.  
4. Scaffold `mobile/ios` with a single Chat screen and hardcoded server URL for Simulator.  
5. Do not add Gmail or wake word until Phase 4–5 exit criteria pass.

---

## 15. One-sentence north star

**Chitti on iPhone is an Odysseus harness with a voice/chat face, a confirm-before-write leash, and tools for life-ops Siri cannot run — not a second Siri.**
