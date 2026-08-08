#!/usr/bin/env bash
# Start the Chitti mobile harness so an iPhone on the same Wi-Fi can reach it.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Optional local env file (never commit secrets).
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT/.env"
  set +a
fi

export CHITTI_HOST="${CHITTI_HOST:-0.0.0.0}"
export CHITTI_PORT="${CHITTI_PORT:-8787}"
export CHITTI_API_KEY="${CHITTI_API_KEY:-dev-key-change-me}"
export CHITTI_POLICY="${CHITTI_POLICY:-safe}"

if [[ -z "${ODYSSEUS_API_KEY:-}" && -z "${GEMINI_API_KEY:-}" ]]; then
  echo "error: set ODYSSEUS_API_KEY or GEMINI_API_KEY (model access)." >&2
  echo "  export ODYSSEUS_API_KEY=..." >&2
  exit 1
fi

# Print LAN hints for the iOS Settings screen.
echo "Chitti mobile harness"
echo "  bind:     http://${CHITTI_HOST}:${CHITTI_PORT}"
echo "  api key:  ${CHITTI_API_KEY}"
echo "  policy:   ${CHITTI_POLICY}"
echo
echo "On this Mac, find an IP the iPhone can reach:"
if command -v ipconfig >/dev/null 2>&1; then
  for iface in en0 en1 en2; do
    ip="$(ipconfig getifaddr "$iface" 2>/dev/null || true)"
    if [[ -n "${ip:-}" ]]; then
      echo "  $iface → http://${ip}:${CHITTI_PORT}"
    fi
  done
elif command -v hostname >/dev/null 2>&1; then
  hostname -I 2>/dev/null | tr ' ' '\n' | while read -r ip; do
    [[ -n "$ip" ]] && echo "  http://${ip}:${CHITTI_PORT}"
  done || true
fi
echo
echo "iPhone Settings → Base URL = http://<mac-lan-ip>:${CHITTI_PORT}"
echo "                 API key  = ${CHITTI_API_KEY}"
echo "Simulator can use          http://127.0.0.1:${CHITTI_PORT}"
echo
echo "Starting server (Ctrl+C to stop)…"
exec python3 -m server
