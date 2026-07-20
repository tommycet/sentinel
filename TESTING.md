# Sentinel — Manual Testing Suite

This guide walks you through testing Sentinel as a real user would. No mocks, no shortcuts.

## Prerequisites

- Python 3.10+
- Docker + Docker Compose (for full SigNoz deployment)
- `curl`
- `openssl` (for HMAC generation)
- `sqlite3` (for DB inspection)

## Quick Start (5 minutes)

### 1. Start Sentinel

```bash
cd /path/to/signoz-sentinel
export SENTINEL_WEBHOOK_SECRET="my-secret-key-change-me"
export SENTINEL_PORT=8090
PYTHONPATH=src python3 -m sentinel --port $SENTINEL_PORT --webhook-secret $SENTINEL_WEBHOOK_SECRET --db-path /tmp/sentinel-test.db
```

Keep this running in a terminal. You should see:
```
Sentinel listening on 127.0.0.1:8090 (dry_run=True, revoker=DryRunRevoker)
```

### 2. Health Check

```bash
curl http://127.0.0.1:8090/livez
```

Expected:
```json
{"status": "ok", "version": "0.1.0"}
```

---

## Test Suite A: Core Webhook Flow

### Test A1: Valid Alert → Quarantine

```bash
# Generate HMAC signature
SECRET="my-secret-key-change-me"
TS=$(date +%s)
BODY='{"status":"firing","alertname":"TestRunaway","startsAt":"2026-07-20T00:00:00Z","labels":{"agent_id":"test-agent","credential_id":"test-cred"}}'
SIG=$(printf '%s' "$TS.$BODY" | openssl dgst -sha256 -mac HMAC -macopt hexkey:$SECRET | awk '{print $2}')

# Send alert
curl -s -X POST http://127.0.0.1:8090/alerts \
  -H "X-Sentinel-Timestamp: $TS" \
  -H "X-Sentinel-Signature: $SIG" \
  -H "Content-Type: application/json" \
  -d "$BODY" | python3 -m json.tool
```

Expected:
```json
{
  "status": "success",
  "incident_id": 1,
  "action": "dry_run",
  "message": "Dry-run: would quarantine credential <HASH>",
  "error": null
}
```

**Note:** The credential hash is SHA-256 of the credential_id. The actual credential is never exposed.

### Test A2: Duplicate Alert → Rejected

```bash
# Use the SAME timestamp+signature+body as Test A1
# (The TS and SIG variables are still set from above)
curl -s -X POST http://127.0.0.1:8090/alerts \
  -H "X-Sentinel-Timestamp: $TS" \
  -H "X-Sentinel-Signature: $SIG" \
  -H "Content-Type: application/json" \
  -d "$BODY" | python3 -m json.tool
```

Expected:
```json
{
  "status": "error",
  "message": "Invalid or expired signature"
}
```

**Why:** The replay protection (`seen_signatures` table) rejects duplicate (timestamp+signature+body) tuples.

### Test A3: Fresh Alert → New Incident

```bash
# New timestamp = new signature = fresh request
TS2=$(date +%s)
SIG2=$(printf '%s' "$TS2.$BODY" | openssl dgst -sha256 -mac HMAC -macopt hexkey:$SECRET | awk '{print $2}')

curl -s -X POST http://127.0.0.1:8090/alerts \
  -H "X-Sentinel-Timestamp: $TS2" \
  -H "X-Sentinel-Signature: $SIG2" \
  -H "Content-Type: application/json" \
  -d "$BODY" | python3 -m json.tool
```

Expected:
```json
{
  "status": "duplicate",
  "incident_id": 1,
  "action": null,
  "message": "Duplicate alert — already processed",
  "error": null
}
```

**Why:** Same idempotency key (fingerprint+agent_id+credential_id) → same incident.

---

## Test Suite B: Release Flow

### Test B1: Release Quarantined Incident

```bash
# Use incident_id from Test A1 (should be 1)
INCIDENT_ID=1
TS3=$(date +%s)
SIG3=$(printf '%s' "$TS3." | openssl dgst -sha256 -mac HMAC -macopt hexkey:$SECRET | awk '{print $2}')

curl -s -X POST http://127.0.0.1:8090/incidents/$INCIDENT_ID/release \
  -H "X-Sentinel-Timestamp: $TS3" \
  -H "X-Sentinel-Signature: $SIG3" \
  -H "Content-Length: 0" | python3 -m json.tool
```

Expected:
```json
{
  "status": "success",
  "action": "released",
  "message": "Dry-run: would release credential <HASH>",
  "error": null
}
```

### Test B2: Release Already-Released Incident → 400

```bash
# Same request as B1
curl -s -X POST http://127.0.0.1:8090/incidents/$INCIDENT_ID/release \
  -H "X-Sentinel-Timestamp: $TS3" \
  -H "X-Sentinel-Signature: $SIG3" \
  -H "Content-Length: 0" | python3 -m json.tool
```

Expected:
```json
{
  "status": "error",
  "message": "Incident 1 is not quarantined (status: released)"
}
```

### Test B3: Release Non-Existent Incident → 404

```bash
curl -s -X POST http://127.0.0.1:8090/incidents/9999/release \
  -H "X-Sentinel-Timestamp: $(date +%s)" \
  -H "X-Sentinel-Signature: dummy" \
  -H "Content-Length: 0" | python3 -m json.tool
```

Expected:
```json
{
  "status": "error",
  "message": "Incident not found"
}
```

### Test B4: Release with Query String

```bash
# Query strings should not break routing
curl -s -X POST "http://127.0.0.1:8090/incidents/1/release?_cachebuster=123" \
  -H "X-Sentinel-Timestamp: $(date +%s)" \
  -H "X-Sentinel-Signature: dummy" \
  -H "Content-Length: 0" | python3 -m json.tool
```

Expected: Same as B2 (400, already released) — query string is ignored for routing.

---

## Test Suite C: Security & Edge Cases

### Test C1: Invalid Signature → 401

```bash
curl -s -X POST http://127.0.0.1:8090/alerts \
  -H "X-Sentinel-Timestamp: $(date +%s)" \
  -H "X-Sentinel-Signature: wrong-signature" \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alertname":"Test","startsAt":"2026-07-20T00:00:00Z","labels":{"agent_id":"a","credential_id":"c"}}' | python3 -m json.tool
```

Expected:
```json
{
  "status": "error",
  "message": "Invalid or expired signature"
}
```

### Test C2: Expired Timestamp → 401

```bash
# Timestamp from 10 minutes ago (outside ±300s window)
OLD_TS=$(( $(date +%s) - 600 ))
SIG_OLD=$(printf '%s' "$OLD_TS.{"status":"firing"}" | openssl dgst -sha256 -mac HMAC -macopt hexkey:$SECRET | awk '{print $2}')

curl -s -X POST http://127.0.0.1:8090/alerts \
  -H "X-Sentinel-Timestamp: $OLD_TS" \
  -H "X-Sentinel-Signature: $SIG_OLD" \
  -H "Content-Type: application/json" \
  -d '{"status":"firing","alertname":"Test","startsAt":"2026-07-20T00:00:00Z","labels":{"agent_id":"a","credential_id":"c"}}' | python3 -m json.tool
```

Expected:
```json
{
  "status": "error",
  "message": "Invalid or expired signature"
}
```

### Test C3: Missing Content-Length → 411

```bash
# Use raw netcat or python to send request without Content-Length
python3 -c "
import socket, hmac, hashlib, time
secret = '$SECRET'
body = b'{\"status\":\"firing\",\"alertname\":\"NoCL\",\"startsAt\":\"2026-07-20T00:00:00Z\",\"labels\":{\"agent_id\":\"a\",\"credential_id\":\"c\"}}'
ts = str(int(time.time()))
sig = hmac.new(secret.encode(), f'{ts}.'.encode() + body, hashlib.sha256).hexdigest()
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.connect(('127.0.0.1', 8090))
req = f'POST /alerts HTTP/1.1\r\nHost: 127.0.0.1:8090\r\nX-Sentinel-Timestamp: {ts}\r\nX-Sentinel-Signature: {sig}\r\nContent-Type: application/json\r\n\r\n'
sock.sendall((req + body.decode()).encode())
print(sock.recv(4096).decode())
sock.close()
"
```

Expected:
```
HTTP/1.0 411 Length Required
Content-Type: application/json

{"status": "error", "message": "Missing Content-Length header"}
```

### Test C4: Oversized Body → 413

```bash
BIG_BODY=$(python3 -c "print('x' * 70000)")
curl -s -X POST http://127.0.0.1:8090/alerts \
  -H "X-Sentinel-Timestamp: $(date +%s)" \
  -H "X-Sentinel-Signature: dummy" \
  -H "Content-Type: application/json" \
  -H "Content-Length: 70000" \
  -d "$BIG_BODY" | python3 -m json.tool
```

Expected:
```json
{
  "status": "error",
  "message": "Body too large: 70000 > 65536"
}
```

---

## Test Suite D: Database Inspection

### Test D1: Verify Incident Table

```bash
sqlite3 /tmp/sentinel-test.db "SELECT id, alertname, status, agent_id, credential_id FROM incidents;"
```

Expected output (after running tests above):
```
1|TestRunaway|released|test-agent|test-cred
```

### Test D2: Verify Actions Audit Trail

```bash
sqlite3 /tmp/sentinel-test.db "SELECT id, incident_id, action_type, status FROM actions;"
```

Expected:
```
1|1|quarantine|pending
2|1|quarantine|success
3|1|release|success
```

### Test D3: Verify Replay Protection Table

```bash
sqlite3 /tmp/sentinel-test.db "SELECT COUNT(*) as replay_count FROM seen_signatures;"
```

Expected: `replay_count >= 1` (each unique signature is recorded)

---

## Test Suite E: Full Foundry Deployment

### Test E1: Validate Foundry Casting

```bash
# Install foundryctl first (see https://signoz.io/foundry.sh)
foundryctl gauge -f casting.yaml
```

Expected: Exit code 0, no errors

### Test E2: Generate Deployment Files

```bash
foundryctl forge -f casting.yaml
```

Expected: Creates `pours/deployment/compose.yaml` and component configs

### Test E3: Patch Compose with Sentinel

```bash
python3 scripts/patch-compose.py
```

Expected: Sentinel service added to `pours/deployment/compose.yaml`

### Test E4: Start Full Stack

```bash
# Requires Docker Compose
docker compose -f pours/deployment/compose.yaml up -d
```

Expected: All SigNoz services + Sentinel running

---

## Test Suite F: SigNoz Integration

### Test F1: Install Dashboard

```bash
# Requires running SigNoz at http://localhost:8080
python3 scripts/install-signoz-assets.py --url http://localhost:8080 --api-key YOUR_API_KEY
```

Expected: Dashboard "Sentinel — Runaway Agent Detection" created

### Test F2: Install Alert Rule

```bash
python3 scripts/install-signoz-assets.py --url http://localhost:8080 --api-key YOUR_API_KEY --alert-only
```

Expected: Alert rule "RunawayToolLoop" created

---

## Test Suite G: Demo Scripts

### Test G1: Run Runaway Agent Simulation

```bash
python3 demo/runaway_agent.py
```

Expected: Output showing 5 normal calls, then 15 identical failing calls, with quarantine trigger at repetition 8

### Test G2: Send Signed Alert via CLI

```bash
python3 demo/send_signed_alert.py http://127.0.0.1:8090/alerts $SECRET
```

Expected: JSON response with `status: "success"` or `status: "duplicate"`

---

## Test Suite H: E2E Script

### Test H1: Full End-to-End

```bash
bash e2e.sh
```

Expected:
```
=== 1. /livez ===
{"status": "ok", "version": "0.1.0"}
[PASS]
=== 2. POST /alerts (signed) ===
...
[PASS] incident_id=1
=== 3. POST /incidents/1/release (via curl + HMAC) ===
...
[PASS] release succeeded
=== E2E OK ===
```

---

## Test Suite I: Unit Tests

### Test I1: Run All Unit Tests

```bash
cd /path/to/signoz-sentinel
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

Expected: `Ran 84 tests in X.XXXs` and `OK`

### Test I2: Run Specific Test Module

```bash
PYTHONPATH=src python3 -m unittest tests.test_app -v
PYTHONPATH=src python3 -m unittest tests.test_auth -v
PYTHONPATH=src python3 -m unittest tests.test_store -v
```

---

## Troubleshooting

### "Invalid or expired signature" on valid requests

- Check `SENTINEL_WEBHOOK_SECRET` matches the secret used to generate signatures
- Ensure timestamp is within ±300 seconds of server time
- Verify the signature is computed as `HMAC-SHA256(secret, f"{timestamp}." + body)`

### "Missing Content-Length header"

- `curl` automatically adds Content-Length. Use raw socket or Python to test without it.

### Database locked

- Sentinel uses SQLite WAL mode. Only one writer at a time. If you see "database is locked", wait and retry.

### Port already in use

- Change `SENTINEL_PORT` or kill the existing process: `pkill -f sentinel`

---

## Expected Results Summary

| Test | Expected Status | Expected Body Key |
|------|----------------|------------------|
| /livez | 200 | `{"status":"ok","version":"0.1.0"}` |
| Valid alert | 200 | `{"status":"success","incident_id":N}` |
| Duplicate alert | 200 | `{"status":"duplicate","incident_id":N}` |
| Replay (same ts+sig+body) | 401 | `{"status":"error","message":"Invalid or expired signature"}` |
| Invalid signature | 401 | `{"status":"error","message":"Invalid or expired signature"}` |
| Expired timestamp | 401 | `{"status":"error","message":"Invalid or expired signature"}` |
| Missing Content-Length | 411 | `{"status":"error","message":"Missing Content-Length header"}` |
| Oversized body | 413 | `{"status":"error","message":"Body too large: ..."}` |
| Release quarantined | 200 | `{"status":"success","action":"released"}` |
| Release already released | 400 | `{"status":"error","message":"... is not quarantined"}` |
| Release non-existent | 404 | `{"status":"error","message":"Incident not found"}` |

---

## Cleanup

```bash
# Stop Sentinel
pkill -f "python3 -m sentinel"

# Remove test database
rm -f /tmp/sentinel-test.db /tmp/sentinel-test.db-*

# Stop Docker Compose (if running)
docker compose -f pours/deployment/compose.yaml down
```
