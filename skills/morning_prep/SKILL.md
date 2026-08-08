description: Prep the user's day from calendar + memory; propose plan, drafts, and optional commits

# Morning prep

Use this skill when the user asks to prep their day, morning briefing, or "what's on my plate".

## Procedure

1. Call `calendar_list` with days=`2` (or the horizon they named).
2. Read any user preferences from memory (already in the system prompt under CHITTI.md).
3. Summarize:
   - Hard commitments (times + places)
   - Gaps for deep work / errands
   - Risks (back-to-back, travel time, missing prep)
4. If something should be scheduled, call `calendar_propose_event` first and show the proposal in your reply. Only call `calendar_commit_event` when they clearly want it created (they will approve on device).
5. If a message should go out (cancel, reschedule, confirm), use `draft_message` — never claim you sent it.
6. Optionally `notes_append` a short plan checklist (requires approval).
7. If they state a lasting preference ("never before 10", "kids pickup Fridays"), call `remember`.
8. End with a short spoken-friendly summary (3–6 sentences): top priorities, next action, one question if blocked.

## Style

- Concrete times, not vibes.
- Prefer questions over silent assumptions when travel time or priorities are unclear.
- Do not invent calendar events that were not listed or committed.
