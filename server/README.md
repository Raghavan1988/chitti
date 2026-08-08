# Chitti mobile harness server

Stdlib HTTP API that runs an Odysseus-shaped agent loop with **life-ops tools** (calendar fixture, drafts, notes, memory, skills) and **confirm-before-write** approvals for the iPhone client.

## Run

From the repo root (preferred — prints LAN URL for iPhone Settings):

```bash
export ODYSSEUS_API_KEY=...          # or GEMINI_API_KEY
export CHITTI_API_KEY=dev-key-change-me
./scripts/run-server.sh
```

Or:

```bash
export ODYSSEUS_API_KEY=...
export CHITTI_API_KEY=dev-key-change-me
export CHITTI_POLICY=safe            # read-only | safe | yolo
python3 -m server
```

Listens on `http://0.0.0.0:8787` by default so devices on the LAN can connect.
Use `http://127.0.0.1:8787` only from the same machine (Simulator / curl).

## Demo client

```bash
# terminal 1
python3 -m server

# terminal 2
export CHITTI_API_KEY=dev-key-change-me
export CHITTI_AUTO_APPROVE=1
python3 demos/mobile_morning_prep.py
```

## API

| Method | Path | Notes |
|--------|------|--------|
| GET | `/health` | no auth |
| POST | `/v1/sessions` | `{"label"}` → `{id}` |
| GET | `/v1/sessions/{id}` | messages + pending approvals |
| GET | `/v1/sessions/{id}/events` | SSE stream |
| POST | `/v1/sessions/{id}/messages` | `{"text"}` → 202, work in background |
| POST | `/v1/sessions/{id}/approvals/{aid}` | `{"approved": true}` |
| GET/PUT | `/v1/memory` | `CHITTI.md` |

All routes except `/health` require `Authorization: Bearer <CHITTI_API_KEY>`.

## Workspace

Default workdir: `server/workspace/` (skills symlinked from repo `skills/`).

- `CHITTI.md` — durable memory  
- `notes.md` — approved note appends  
- `drafts/` — message drafts  
- `.chitti/calendar_events.json` — committed calendar state (seeded from fixture)  
- `.odysseus/sessions/` — JSONL transcripts  
