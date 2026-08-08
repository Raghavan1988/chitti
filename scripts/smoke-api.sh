#!/usr/bin/env bash
# Quick health check against a running server (no model call).
set -euo pipefail

BASE="${CHITTI_BASE:-http://127.0.0.1:8787}"
KEY="${CHITTI_API_KEY:-dev-key-change-me}"

echo "GET $BASE/health"
curl -fsS "$BASE/health"
echo
echo "POST $BASE/v1/sessions"
curl -fsS -X POST "$BASE/v1/sessions" \
  -H "Authorization: Bearer $KEY" \
  -H "Content-Type: application/json" \
  -d '{"label":"smoke"}'
echo
echo "ok"
