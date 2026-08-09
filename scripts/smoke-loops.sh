#!/usr/bin/env bash
# SignalLoop command-bus smoke test. No model API key required.
#
# Exercises the LoopEngine over HTTP: loop CRUD, evidence, status projection,
# command idempotency, and the externalize review-token gate (no silent send).
#
# Assumes a server is already running (see scripts/run-server.sh). Override
# CHITTI_BASE / CHITTI_API_KEY to point at a specific instance.
set -euo pipefail

BASE="${CHITTI_BASE:-http://127.0.0.1:8787}"
KEY="${CHITTI_API_KEY:-dev-key-change-me}"
AUTH="Authorization: Bearer ${KEY}"
JSON="Content-Type: application/json"

# post <json> -> response body on stdout
post() { curl -fsS -X POST "$BASE/v1/commands" -H "$AUTH" -H "$JSON" -d "$1"; }
get() { curl -fsS "$BASE$1" -H "$AUTH"; }

# jget <key-path>: read JSON from stdin, print a value (python3, stdlib only).
jget() { python3 -c 'import sys,json;d=json.load(sys.stdin)
p=sys.argv[1].split(".")
for k in p:
    d=d[int(k)] if k.isdigit() else d[k]
print(d)' "$1"; }

# assert_eq <label> <actual> <expected>
assert_eq() {
  if [[ "$2" != "$3" ]]; then
    echo "FAIL: $1: expected '$3', got '$2'" >&2
    exit 1
  fi
  echo "  ok: $1 == $3"
}

echo "== health =="
get /health >/dev/null && echo "  ok: health"

echo "== new_loop (idempotency_key=k-new-1) =="
R=$(post '{"type":"new_loop","source":"app","idempotency_key":"k-new-1","payload":{"title":"Ship SignalLoop Phase 1","domain":"career","why_it_matters":"proof of progress","text":"kickoff note"}}')
LOOP=$(echo "$R" | jget loop_id)
assert_eq "new_loop.idempotent" "$(echo "$R" | jget idempotent)" "False"
echo "  loop_id=$LOOP"

echo "== new_loop REPLAY (same key must not duplicate) =="
R2=$(post '{"type":"new_loop","source":"app","idempotency_key":"k-new-1","payload":{"title":"DUPLICATE ATTEMPT","domain":"life"}}')
assert_eq "replay.loop_id" "$(echo "$R2" | jget loop_id)" "$LOOP"
assert_eq "replay.idempotent" "$(echo "$R2" | jget idempotent)" "True"

echo "== list_loops (exactly one) =="
assert_eq "loops.count" "$(get /v1/loops | jget 'loops' | python3 -c 'import sys;print(len(eval(sys.stdin.read())))')" "1"

echo "== log_evidence =="
R=$(post "{\"type\":\"log_evidence\",\"source\":\"share\",\"idempotency_key\":\"k-ev-1\",\"payload\":{\"loop_id\":\"$LOOP\",\"kind\":\"url\",\"url\":\"https://example.com/proof\"}}")
assert_eq "log_evidence.ok" "$(echo "$R" | jget ok)" "True"

echo "== status board + locked projection =="
get /v1/status | jget open >/dev/null && echo "  ok: status.open present"
SPOKEN=$(get '/v1/status?locked=1' | jget spoken)
echo "  locked spoken: \"$SPOKEN\""

echo "== add_draft (safe; not externalized) =="
R=$(post "{\"type\":\"add_draft\",\"source\":\"app\",\"idempotency_key\":\"k-draft-1\",\"payload\":{\"loop_id\":\"$LOOP\",\"kind\":\"email\",\"content\":\"Hi team, sharing proof...\"}}")
DRAFT=$(echo "$R" | jget draft_id)
echo "  draft_id=$DRAFT"

echo "== externalize WITHOUT token -> safe refusal =="
R=$(post "{\"type\":\"externalize\",\"source\":\"siri\",\"idempotency_key\":\"k-ext-1\",\"payload\":{\"loop_id\":\"$LOOP\",\"draft_id\":\"$DRAFT\"}}")
assert_eq "externalize.blocked" "$(echo "$R" | jget externalized)" "False"
assert_eq "externalize.reason" "$(echo "$R" | jget reason)" "review_required"

echo "== request_review -> resolve_review(approved) -> token =="
R=$(post "{\"type\":\"request_review\",\"source\":\"app\",\"idempotency_key\":\"k-rev-1\",\"payload\":{\"loop_id\":\"$LOOP\",\"action\":\"send email\",\"draft_id\":\"$DRAFT\"}}")
REVIEW=$(echo "$R" | jget review_id)
R=$(post "{\"type\":\"resolve_review\",\"source\":\"app\",\"idempotency_key\":\"k-rev-resolve-1\",\"payload\":{\"review_id\":\"$REVIEW\",\"approved\":true}}")
TOKEN=$(echo "$R" | jget review_token)
echo "  review_token=$TOKEN"

echo "== externalize WITH token -> success =="
R=$(post "{\"type\":\"externalize\",\"source\":\"app\",\"idempotency_key\":\"k-ext-2\",\"payload\":{\"loop_id\":\"$LOOP\",\"draft_id\":\"$DRAFT\",\"review_token\":\"$TOKEN\"}}")
assert_eq "externalize.ok" "$(echo "$R" | jget externalized)" "True"

echo "== externalize REPLAY (idempotent, no double send) =="
R=$(post "{\"type\":\"externalize\",\"source\":\"app\",\"idempotency_key\":\"k-ext-2\",\"payload\":{\"loop_id\":\"$LOOP\",\"draft_id\":\"$DRAFT\",\"review_token\":\"$TOKEN\"}}")
assert_eq "externalize.replay.idempotent" "$(echo "$R" | jget idempotent)" "True"

echo
echo "ALL SMOKE CHECKS PASSED"
