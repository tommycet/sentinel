#!/usr/bin/env bash
# Sentinel E2E: start service, send signed alert, verify response, release, verify release.
set -euo pipefail
cd "$(dirname "$0")"

SECRET="${SENTINEL_WEBHOOK_SECRET:-test-secret}"
PORT="${SENTINEL_PORT:-8095}"
DB=$(mktemp -u /tmp/sentinel-e2e-XXXX.db)
HOST=127.0.0.1

PYTHONPATH=src python3 -m sentinel --port "$PORT" --webhook-secret "$SECRET" --db-path "$DB" --dry-run &
PID=$!
cleanup() { kill "$PID" 2>/dev/null || true; wait "$PID" 2>/dev/null || true; rm -f "$DB" "$DB"-wal "$DB"-shm; }
trap cleanup EXIT

for i in $(seq 1 30); do
  if curl -sf "http://$HOST:$PORT/livez" >/dev/null 2>&1; then break; fi
  sleep 0.2
done

echo "=== 1. /livez ==="
LIVEZ=$(curl -sf "http://$HOST:$PORT/livez")
echo "$LIVEZ"
echo "$LIVEZ" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="ok" and d["version"], "bad livez"'
echo "[PASS]"

echo "=== 2. POST /alerts (signed) ==="
RESP=$(python3 demo/send_signed_alert.py "http://$HOST:$PORT/alerts" "$SECRET")
echo "$RESP" | python3 -m json.tool
INCIDENT_ID=$(echo "$RESP" | python3 -m json.tool | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["body"]["status"]=="success", f"expected success got {d}"; print(d["body"]["incident_id"])')
echo "[PASS] incident_id=$INCIDENT_ID"

echo "=== 3. POST /incidents/$INCIDENT_ID/release (via curl + HMAC) ==="
TS=$(date +%s)
SIG=$(echo -n "$TS." | openssl dgst -sha256 -hmac "$SECRET" | cut -d' ' -f2)
REL_RESP=$(curl -sf -X POST "http://$HOST:$PORT/incidents/$INCIDENT_ID/release" \
  -H "X-Sentinel-Timestamp: $TS" \
  -H "X-Sentinel-Signature: $SIG" \
  -H "Content-Length: 0")
echo "$REL_RESP"
echo "$REL_RESP" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d["status"]=="success" and d["action"]=="released", f"release failed: {d}"'
echo "[PASS] release succeeded"

echo "=== E2E OK ==="
