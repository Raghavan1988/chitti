description: Find the right people to connect with and posts to comment on for a loop, and draft the outreach — never send

# Engagement (career/life)

Use this skill when the user wants to grow the *right* network or presence for an open loop —
"who should I connect with about X", "find posts worth commenting on", "help me engage on
X/LinkedIn for this goal". It turns a loop's target into concrete, reviewable outreach. It
**drafts only** — connecting, commenting, following, or posting is an *externalization* that only
happens on device through an authenticated foreground review. Nothing is ever sent from here.

The server unit behind this is `server/scout.py` (`POST /v1/scout`): it asks a **connector** for
candidate people/posts, scores them against the loop, and writes `connect` / `comment` drafts via
the LoopCommandBus. This skill is the agent-facing procedure for the same shape.

## Procedure

1. **Anchor to a loop.** Engagement always serves a specific loop (a role, company, lab, topic, or
   life goal). If there is no loop yet, create one first (see `opportunity`). State the target and
   the desired outcome in one line.
2. **Derive the topic.** Pull the loop's real vocabulary from its title, why-it-matters, steps, and
   evidence. Do not invent interests the user has not expressed.
3. **Discover candidates.** Use the available connector / read tools (or `POST /v1/scout`) to list
   candidate **people** (worth a connect note) and **posts** (worth a comment). Only use authorized
   sources — official APIs or an explicit user-provided list. **Never scrape at scale.**
4. **Rank by fit, explain it.** Prefer candidates whose work genuinely overlaps the loop. For each,
   name the *matched topics* so the user can judge relevance — "overlaps with inference,
   infrastructure", not "great match".
5. **Draft, never send.** For each kept candidate, prepare a short, specific draft:
   - *connect*: reference the shared topic and the loop; ask to connect and compare notes.
   - *comment*: react to the actual post; add one genuine idea or question.
   Attach them as reviewable drafts. Never claim anything was connected, commented, or sent.
6. **Stay idempotent.** Re-running for the same loop on the same day must not duplicate drafts or
   re-suggest the same person. Surface only genuinely new candidates on later passes.
7. **Close with a plan.** 3–6 spoken-friendly sentences: the top 1–2 people to connect with, the
   top 1–2 posts to comment on, why each fits, and the reminder that sending is a reviewed action.

## Guardrails

- Draft-level only. Connecting / commenting / following / posting is a foreground-reviewed
  externalization (review token) — never here, never from a background or cloud job.
- No scraping LinkedIn/X at scale, and no mass outreach — that risks trust and account bans.
- No fabricated credentials, shared history, or flattery in any draft.
- Explain relevance with concrete matched topics; prefer a few high-fit candidates over a long list.
- Respect platform terms of service: discovery + human-reviewed drafting, not click automation.
