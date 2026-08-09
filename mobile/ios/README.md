# SignalLoop / Chitti iOS

SwiftUI client for the mobile harness. Product direction: **SignalLoop** (career + life loops).  
Full product rules: repo root [`plan.md`](../../plan.md), [`AGENTS.md`](../../AGENTS.md).  
Mac handoff: [`CONTINUE_ON_MAC.md`](../../CONTINUE_ON_MAC.md).

## Prerequisites

- Mac with **Xcode 15+** (iOS 17 SDK)
- Apple ID for signing
- Python 3.10+ (for local `./scripts/run-server.sh`)
- Model API key: `ODYSSEUS_API_KEY` or `OPENAI_API_KEY`

## Run (Mac)

```bash
# from repo root
export ODYSSEUS_API_KEY=...
export CHITTI_API_KEY=dev-key-change-me
./scripts/run-server.sh

open mobile/ios/Chitti.xcodeproj
```

### Xcode

1. Target **Chitti** → Signing → **Team**
2. Unique bundle id if `com.chitti.app` conflicts
3. Scheme **Chitti** (shared) → Simulator or device → Run

### App Settings

| | Simulator | Device |
|--|-----------|--------|
| Base URL | `http://127.0.0.1:8787` | `http://<mac-lan-ip>:8787` |
| API key | `CHITTI_API_KEY` | same |

## Layout

```
mobile/ios/
  Chitti.xcodeproj/          shared scheme included
  Chitti/
    ChittiApp.swift
    Models.swift
    Info.plist               mic, speech, local networking
    Services/                REST, SSE, speech
    Features/                Chat, Settings, Approvals
```

## Current vs next

| Today | Next (SignalLoop) |
|-------|-------------------|
| Chat + voice + server tools | **Loop** list/detail UI |
| Approval cards for server tools | **ReviewAction** + foreground review for send/post/calendar |
| Settings → API | **LoopCommandBus** (core without AppIntents) |
| — | App Intents: NewLoop, LogEvidence, Status, Pause/Resume, ApprovePlan, ReviewAction, MarkComplete |
| — | In-app twin for every intent (standalone parity) |

Do **not** implement planning inside intent handlers. Do **not** add a general Siri “Approve send.”

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Cannot connect | Same Wi‑Fi? LAN IP? Server up? Firewall? |
| 401 | API key mismatch |
| No model reply | `ODYSSEUS_API_KEY` / `OPENAI_API_KEY` on server |
| Signing | Team + unique bundle id + trust cert on device |
| Cleartext HTTP | Info.plist allows local networking; use `http://` LAN IP |

## Architecture (dev today)

```
iPhone app  →  HTTP/SSE  →  python3 -m server  →  model + tools
```

Long-term product: more LoopEngine on device + cloud wake plane (see `plan.md`)—still **no user Mac agent node**.
