# Continue on Mac + Xcode

You are picking up **SignalLoop** development on a Mac. This repo was prepared so you can clone, run the API, and open the iOS project without prior Linux context.

## Product north star (read first)

| Doc | Why |
|-----|-----|
| [`plan.md`](plan.md) | SignalLoop product + architecture (career + life loops, Siri boundary, command bus, cloud wake, no Mac *node*) |
| [`AGENTS.md`](AGENTS.md) | Implementation invariants for coding agents |

**SignalLoop** = multi-day **loops** (`career` | `life` | `both`).  
**Siri** = optional App Intents adapter (not a dependency).  
**This Mac** = where you build the **iPhone app** with Xcode.  
**Not** a “desktop agent node” for users—see plan non-goals.

## Prerequisites

- macOS with **Xcode 15+** (iOS 17+ SDK)
- Apple ID (free OK for personal device)
- Python 3.10+
- `ODYSSEUS_API_KEY` or `OPENAI_API_KEY` (model)
- iPhone on same Wi‑Fi as Mac (for device testing)

## 1. Clone

```bash
git clone https://github.com/Raghavan1988/chitti.git
cd chitti
git pull origin main
```

Optional env file:

```bash
cp .env.example .env
# edit .env — never commit it
```

## 2. Start the harness API (same Mac)

```bash
export ODYSSEUS_API_KEY=your_key_here   # or OPENAI_API_KEY
export CHITTI_API_KEY=dev-key-change-me
chmod +x scripts/*.sh
./scripts/run-server.sh
```

Leave this running. Note the printed **LAN URL** (e.g. `http://192.168.1.42:8787`).

Smoke (optional, other terminal):

```bash
./scripts/smoke-api.sh
```

CLI agent demo (optional):

```bash
export CHITTI_AUTO_APPROVE=1
python3 demos/mobile_morning_prep.py
```

## 3. Open iOS project

```bash
open mobile/ios/Chitti.xcodeproj
```

In Xcode:

1. Target **Chitti** → **Signing & Capabilities** → your **Team**
2. Unique **Bundle ID** if needed (`com.chitti.app` → e.g. `com.yourname.signalloop`)
3. Destination: **Simulator** first, then physical **iPhone**
4. Run ▶

On a physical device: **Settings → General → VPN & Device Management** → trust developer cert.

## 4. Point the app at the server

In the app **Settings** tab:

| Field | Simulator | Physical iPhone |
|-------|-----------|-----------------|
| Base URL | `http://127.0.0.1:8787` | `http://<mac-lan-ip>:8787` |
| API key | same as `CHITTI_API_KEY` | same |

**Never use `127.0.0.1` on a real iPhone** (that is the phone itself).

## 5. What works today vs build next

### Already in repo

| Area | Status |
|------|--------|
| Odysseus coding harness (`odysseus/`) | Working demos |
| Python mobile API (`server/`) | Sessions, SSE, calendar fixture, drafts, memory, skills, approvals |
| SwiftUI shell | Chat, voice (push-to-talk), approvals cards, settings |
| Xcode project | `mobile/ios/Chitti.xcodeproj` |
| Product plan | SignalLoop in `plan.md` |

### Priority on Mac (SignalLoop)

Follow `plan.md` phases; do **not** put planning inside App Intents.

1. **In-app first (standalone parity)**  
   Loop list/detail UI, create/log/status/pause, review sheet for externalize  
2. **LoopCommandBus + LoopEngine** (core must not `import AppIntents`)  
3. **App Intents adapters** (twins of in-app actions):  
   `NewLoop`, `LogEvidence`, `Status`, `Pause`/`Resume`, `ApprovePlan`, `ReviewAction`, `MarkComplete`  
4. **Privacy-safe Status** (no sensitive content on lock screen speech)  
5. Later: Gmail OAuth, cloud wake plane, `weekly_proof` skill  

## 6. Invariants (do not violate)

- No Siri-only core features  
- No general voice “Approve” that sends email / posts / commits calendar  
- No Mac-as-agent-node / desktop-use bridge for users  
- No Notification Center / Messages scraping  
- Background jobs may research/draft/notify only—not silent send  

Full list: `AGENTS.md`.

## 7. Suggested first session on Mac

```text
[ ] git clone + pull
[ ] run-server.sh + smoke-api.sh
[ ] open Xcode, sign, run on Simulator
[ ] chat: morning prep / calendar list (server path)
[ ] read plan.md §1–4 and AGENTS.md “SignalLoop product invariants”
[ ] sketch Loop list UI (even stub) before Siri intents
```

## 8. Helpful paths

```text
plan.md                 product + architecture
AGENTS.md               coding agent rules
README.md               human overview
mobile/ios/README.md    iOS detail
server/README.md        API
.env.example            env vars
skills/                 SKILL.md packs
```

## 9. Remote

```text
https://github.com/Raghavan1988/chitti
branch: main
```
