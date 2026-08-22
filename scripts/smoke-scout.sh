#!/usr/bin/env bash
# SignalLoop engagement-scout smoke test. No model API key required.
#
# Exercises the platform-agnostic engagement pipeline end to end against a
# running server: create a loop, run the scout (offline StubConnector), and
# assert it drafts reviewable connect/comment actions, is idempotent per day
# (no duplicate drafts on re-run), and externalizes NOTHING without a review.
#
# Assumes a server is already running (see scripts/run-server.sh). Override
# CHITTI_BASE / CHITTI_API_KEY to point at a specific instance.
set -euo pipefail

BASE="${CHITTI_BASE:-http://127.0.0.1:8787}"
KEY="${CHITTI_API_KEY:-dev-key-change-me}"
AUTH="Authorization: ******"
JSON="Content-Type: application/json"
RUN="$(date +%s)"  # unique per invocation so first-run asserts hold on re-runs

cmd()   { curl -fsS -X POST "$BASE/v1/commands" -H "$AUTH" -H "$JSON" -d "$1"; }
scout() { curl -fsS -X POST "$BASE/v1/scout"    -H "$AUTH" -H "$JSON" -d "$1"; }
get()   { curl -fsS "$BASE$1" -H "$AUTH"; }

# jget <key-path>: read JSON from stdin, print a value (python3, stdlib only).
jget() { python3 -c 'import sys,json;d=json.load(sys.stdin)
p=sys.argv[1].split(".")
for k in p:
    d=d[int(k)] if k.isdigit() else d[k]
print(d)' "$1"; }

assert_eq() {
  if [[ "$2" != "$3" ]]; then
    echo "FAIL: $1: expected '$3', got '$2'" >&2
    exit 1
  fi
  echo "  ok: $1 == $3"
}
assert_ge() {
  if (( $2 < $3 )); then
    echo "FAIL: $1: expected >= $3, got $2" >&2
    exit 1
  fi
  echo "  ok: $1 ($2) >= $3"
}

echo "== health =="
get /health >/dev/null && echo "  ok: health"

echo "== new_loop (engagement target) =="
R=$(cmd "{\"type\":\"new_loop\",\"source\":\"app\",\"idempotency_key\":\"scout-loop-$RUN\",\"payload\":{\"title\":\"Break into frontier AI agent infrastructure\",\"domain\":\"career\",\"why_it_matters\":\"ship proof of agent systems and inference infrastructure\"}}")
LOOP=$(echo "$R" | jget loop_id)
echo "  loop_id=$LOOP"

echo "== scout (offline stub connector) =="
R=$(scout "{\"loop_id\":\"$LOOP\"}")
CAND=$(echo "$R" | jget 'scouted.0.candidates')
CONN=$(echo "$R" | jget 'scouted.0.connect')
COMM=$(echo "$R" | jget 'scouted.0.comment')
NEW=$(echo "$R" | jget 'scouted.0.new')
WHO=$(echo "$R" | jget 'scouted.0.connector')
echo "  connector=$WHO candidates=$CAND connect=$CONN comment=$COMM new=$NEW"
assert_ge "scout.candidates" "$CAND" 1
assert_ge "scout.connect"    "$CONN" 1
assert_ge "scout.comment"    "$COMM" 1
assert_eq "scout.new==candidates(first run)" "$NEW" "$CAND"

echo "== drafts attached, correct kinds, none externalized =="
STATS=$(get "/v1/loops/$LOOP" | python3 -c 'import sys,json
loop=json.load(sys.stdin)
ds=loop["drafts"]
kinds=sorted({d["kind"] for d in ds})
ext=sum(1 for d in ds if d.get("externalized"))
print(len(ds), ",".join(kinds), ext)')
NDRAFTS=$(echo "$STATS" | cut -d" " -f1)
KINDS=$(echo "$STATS" | cut -d" " -f2)
EXT=$(echo "$STATS" | cut -d" " -f3)
echo "  drafts=$NDRAFTS kinds=$KINDS externalized=$EXT"
assert_ge "drafts.count" "$NDRAFTS" 2
assert_eq "drafts.externalized" "$EXT" "0"
case ",$KINDS," in *,connect,*) echo "  ok: has connect drafts";; *) echo "FAIL: no connect drafts ($KINDS)" >&2; exit 1;; esac
case ",$KINDS," in *,comment,*) echo "  ok: has comment drafts";; *) echo "FAIL: no comment drafts ($KINDS)" >&2; exit 1;; esac

echo "== scout REPLAY same day -> idempotent (no new drafts) =="
R=$(scout "{\"loop_id\":\"$LOOP\"}")
NEW2=$(echo "$R" | jget 'scouted.0.new')
CACHED=$(echo "$R" | jget 'scouted.0.cached')
assert_eq "scout.replay.new"    "$NEW2"   "0"
assert_eq "scout.replay.cached" "$CACHED" "True"
NDRAFTS2=$(get "/v1/loops/$LOOP" | python3 -c 'import sys,json;print(len(json.load(sys.stdin)["drafts"]))')
assert_eq "drafts.count.stable" "$NDRAFTS2" "$NDRAFTS"

echo "== a connect draft cannot externalize without review (safe refusal) =="
DRAFT=$(get "/v1/loops/$LOOP" | python3 -c 'import sys,json
for d in json.load(sys.stdin)["drafts"]:
    if d["kind"]=="connect":
        print(d["id"]); break')
R=$(cmd "{\"type\":\"externalize\",\"source\":\"siri\",\"idempotency_key\":\"scout-ext-$RUN\",\"payload\":{\"loop_id\":\"$LOOP\",\"draft_id\":\"$DRAFT\"}}")
assert_eq "externalize.blocked" "$(echo "$R" | jget externalized)" "False"
assert_eq "externalize.reason"  "$(echo "$R" | jget reason)"       "review_required"

echo
echo "ALL SCOUT SMOKE CHECKS PASSED"
