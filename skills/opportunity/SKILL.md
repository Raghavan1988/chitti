description: Research a target role or lab and map the proof gaps to close before any outreach

# Opportunity (career)

Use this skill when the user names something to pursue — a role, company, lab, or person
("help me go after X", "prep me for this job", "what do I need to land Y"). It turns a vague
ambition into a career loop with evidence and a concrete proof plan. It **drafts only** — nothing
is ever sent from here; externalizing happens on device via authenticated foreground review.

## Procedure

1. **Frame the loop.** State the target in one line: role/lab, why it matters, and the desired
   outcome (interview, referral, offer, collaboration). If specifics are missing, ask one focused
   question instead of guessing.
2. **Gather signal.** Use whatever read tools are available (`web_search` / `fetch_url` /
   `gmail_search` when present) to pull the role's requirements, the team's recent work, and any
   prior contact. If no research tools are wired, ask the user to paste the JD, the lab page, or the
   thread — do not invent details.
3. **Map proof gaps.** Compare what the target visibly values against what the user can already
   prove. Split into: (a) already proven, (b) partial, (c) missing. Be specific — "shipped and
   measured an X", not "strong skills".
4. **Pick the smallest proof.** Choose ONE artifact that closes the highest-value gap and is
   shippable this week (hand off to the `weekly_proof` skill if present). Everything else becomes
   later loop steps.
5. **Record it.** `remember` durable facts worth keeping (target, key people, hard constraints).
   Use `notes_append` for the proof checklist (this requires user approval).
6. **Draft, never send.** If outreach is warranted, prepare it with `draft_message` / `draft_post`
   — but only *after* there is real proof to point to (see `outreach_after_proof`). Never claim a
   message was sent; sending is a reviewed action on device.
7. **Close with a plan.** 3–6 spoken-friendly sentences: the target, the one proof to ship next, the
   gap it closes, and one open question if blocked.

## Guardrails

- Draft-level only. Sending, posting, or committing is a foreground-reviewed action — never here.
- No fabricated credentials, publications, or experience in any draft.
- Prefer one concrete next proof over a long generic plan.
- Ask before assuming seniority, location, relocation, or compensation.
