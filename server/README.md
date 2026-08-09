# Chitti mobile harness server

Stdlib HTTP API that runs an Odysseus-shaped agent loop with **life-ops tools** (calendar fixture, drafts, notes, memory, skills) and **confirm-before-write** approvals for the iPhone client.

It also hosts the **SignalLoop command bus** (`POST /v1/commands`): an idempotent LoopEngine that persists career/life **loops** and gates any externalize (send/post/commit) behind a review token — no silent side effects.

## Run

From the repo root (preferred — prints LAN URL for iPhone Settings):

```bash
export ODYSSEUS_API_KEY=...          # or OPENAI_API_KEY
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

> Requires **Python 3.10+** (the server uses `X | None` type syntax). `run-server.sh` auto-selects a suitable interpreter; for the manual form use e.g. `python3.12 -m server` if your default `python3` is older.

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

### SignalLoop command bus

Every surface (app, Siri adapter, share, widget) submits **commands** here; all
planning/policy lives in the LoopEngine, never in the caller.

| Method | Path | Notes |
|--------|------|--------|
| POST | `/v1/commands` | `{type, payload, source, idempotency_key}` → idempotent result |
| POST | `/v1/suggest` | `{loop_id?, force?}` → draft today's suggested next action(s) |
| GET | `/v1/loops` | all loops (most-recent first) |
| GET | `/v1/loops/{id}` | one loop |
| GET | `/v1/status` | status board; `?locked=1` → privacy-safe projection |
| GET | `/v1/reviews` | pending consequential-action reviews |

**Command types:** `new_loop`, `update_loop`, `log_evidence`, `add_draft`,
`pause`, `resume`, `approve_plan`, `mark_complete`, `request_review`,
`resolve_review`, `externalize`, `remember`.

**Suggested actions:** `POST /v1/suggest` runs each active loop's context
through the model and writes back the top `next_action` plus a review-safe
`suggestion` draft — never externalizing. It is **idempotent per loop-per-day**
(a same-day retry is a no-op that returns `cached: true` without a model call);
pass `{"force": true}` for an intentional refresh, or `{"loop_id": "..."}` to
target one loop. This is the reusable per-loop unit a daily **cloud wake** job
will call; today it is triggered on demand.

**Safety:** `externalize` (send/post/commit a draft) requires a `review_token`
minted by `resolve_review`; without a valid token it refuses safely. Smoke:
`./scripts/smoke-loops.sh` (no model key needed).

## Workspace

Default workdir: `server/workspace/` (skills symlinked from repo `skills/`).

- `CHITTI.md` — durable memory  
- `notes.md` — approved note appends  
- `drafts/` — message drafts  
- `.chitti/calendar_events.json` — committed calendar state (seeded from fixture)  
- `.chitti/loops.json` — SignalLoop loops, reviews, facts, idempotency keys  
- `.odysseus/sessions/` — JSONL transcripts  
