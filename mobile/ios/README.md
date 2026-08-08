# Chitti iOS — run on iPhone from a Mac

SwiftUI client for the Chitti mobile harness. Open the Xcode project in this
folder, run the Python server on the same Mac (or LAN), then install to your
device.

## Prerequisites

- Mac with **Xcode 15+** (iOS 17 SDK)
- Free or paid **Apple ID** for signing
- Physical **iPhone** on the **same Wi‑Fi** as the Mac (or USB + local network)
- **Python 3.10+** on the Mac
- **Gemini / Odysseus API key** for the model

## 1. Clone and start the harness

```bash
git clone https://github.com/Raghavan1988/chitti.git
cd chitti

export ODYSSEUS_API_KEY=your_key_here   # or GEMINI_API_KEY
export CHITTI_API_KEY=dev-key-change-me

chmod +x scripts/run-server.sh
./scripts/run-server.sh
```

The script prints LAN URLs like `http://192.168.x.x:8787`. Leave this terminal open.

Optional smoke test (second terminal):

```bash
./scripts/smoke-api.sh
```

## 2. Open the iOS app

```bash
open mobile/ios/Chitti.xcodeproj
```

In Xcode:

1. Select the **Chitti** target → **Signing & Capabilities**
2. Enable **Automatically manage signing**
3. Choose your **Team** (your Apple ID)
4. If the bundle id `com.chitti.app` conflicts, change it to something unique
   (e.g. `com.yourname.chitti`)
5. Plug in the iPhone, unlock it, trust the computer if asked
6. Top bar: pick your **iPhone** as the run destination (not a simulator)
7. Press **Run** (▶)

First install: on the iPhone go to  
**Settings → General → VPN & Device Management** → trust your developer certificate.

## 3. Point the app at the server

In the app **Settings** tab:

| Field | Physical iPhone | Simulator |
|-------|-----------------|-----------|
| Base URL | `http://<mac-lan-ip>:8787` from `run-server.sh` | `http://127.0.0.1:8787` |
| API key | same as `CHITTI_API_KEY` | same |

Tap **Save connection**.

## 4. Try a task

In **Chat**:

```text
Prep my day. Load the morning_prep skill and summarize my calendar.
```

Or hold the **mic** for push-to-talk.

When the agent wants to commit a calendar event or append notes, an **Approval**
card appears — tap **Approve** or **Reject**.

## Layout

```
mobile/ios/
  Chitti.xcodeproj/     open this in Xcode
  Chitti/
    ChittiApp.swift
    Models.swift
    Info.plist          mic, speech, local networking
    Services/           REST + SSE + speech
    Features/           Chat, Settings, Approvals
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Could not connect | Same Wi‑Fi? Correct LAN IP? Server still running? Firewall allowing 8787? |
| 401 unauthorized | API key in app must match `CHITTI_API_KEY` |
| No model reply | Set `ODYSSEUS_API_KEY` / `GEMINI_API_KEY` on the Mac before `run-server.sh` |
| Mic / speech fails | Allow microphone + speech recognition when iOS prompts |
| Signing errors | Pick a Team; unique bundle id; trust developer cert on device |
| Cleartext HTTP blocked | `Info.plist` already allows local networking; use `http://` LAN IP not `https://` |

## Architecture (short)

```
iPhone app  --HTTP/SSE-->  python3 -m server (Mac)  --HTTPS-->  model API
                              life-ops tools + approvals
```

The phone never holds the model key; only the Mac server does.
