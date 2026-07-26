# Sentinel — Closed-Loop Agent Runaway Detection

**Observability becomes enforcement.** Sentinel detects runaway AI agents from OpenTelemetry signals, quarantines credentials, and records evidence — all through SigNoz-native webhooks.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-102-green.svg)](tests/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](src/)

## What It Does

Sentinel sits between your SigNoz alerting pipeline and your agent infrastructure. When an agent exceeds its resource budget, Sentinel:

1. **Receives** a signed webhook from SigNoz (HMAC-SHA256 + replay protection)
2. **Parses** the incident: agent ID, model, token count, vault access, DB mutations
3. **Quarantines** the agent's credentials (vault keys, DB sessions, API tokens)
4. **Records** full lineage: brain capture → LLM response → vault read → DB mutation → API call
5. **Exports** OTLP traces back to SigNoz for dashboards and correlation
6. **Releases** on human approval via `POST /incidents/{id}/release`

## Architecture

```
SigNoz Alert Webhook
        │
        ▼
┌─────────────────────┐
│  HMAC-SHA256 Verify  │  ← replay guard (301s TTL)
├─────────────────────┤
│  Incident Parser     │  ← SigNoz alert format
├─────────────────────┤
│  SQLite Store        │  ← idempotent, WAL mode
├─────────────────────┤
│  AgentLineage Graph  │  ← brain-capture → vault → DB → API
├─────────────────────┤
│  Revoker             │  ← vault / DB / API revocation
├─────────────────────┤
│  OTLP Export         │  ← traces back to SigNoz
└─────────────────────┘
```

## Quick Start

```bash
git clone https://github.com/sigaz/sentinel.git
cd sentinel
pip install -e .

# Run (dry-run mode by default — no credentials revoked)
python -m sentinel --port 8090 --webhook-secret YOUR_SECRET --dry-run

# Verify
curl http://localhost:8090/health
```

## Provider Configuration

Sentinel supports multiple LLM providers globally:

| Provider | Setup | Free Tier |
|----------|-------|-----------|
| **9router** | Default gateway, 40+ providers | Yes |
| **Groq** | `GROQ_API_KEY=gsk_...` | 200 req/day |
| **OpenRouter** | `OPENROUTER_API_KEY=sk-or-...` | 27+ free models |

```bash
# Environment variables
GROQ_API_KEY=gsk_...
OPENROUTER_API_KEY=sk-or-...
SENTINEL_WEBHOOK_SECRET=your-secret
SENTINEL_DB_PATH=./sentinel.db
SENTINEL_OTEL_ENDPOINT=http://localhost:4317
```

## API Reference

### Health Check
```bash
GET /health
# → {"status": "ok", "version": "0.1.0"}
```

### Submit Alert
```bash
POST /alerts
Headers:
  X-Sentinel-Timestamp: <unix_timestamp>
  X-Sentinel-Signature: sha256=<hmac_signature>
Body: <signoz_alert_json>
```

### Query AgentLineage
```bash
GET /agent-lineage?id=incident_001
GET /agent-lineage?model=groq/llama-3.3-70b-versatile
GET /agent-lineage?agent=hermes-brain-capture
GET /agent-lineage?from=2026-07-26T00:00:00Z&to=2026-07-26T23:59:59Z
```

### Release Incident
```bash
POST /incidents/{id}/release
Body: {"reason": "Reviewed and approved", "revoke_vault": true}
# → 204 No Content with audit trail
```

## Project Structure

```
sentinel/
├── src/sentinel/
│   ├── __main__.py       # CLI entry point
│   ├── app.py            # HTTP server (BaseHTTPRequestHandler)
│   ├── auth.py           # HMAC-SHA256 webhook verification
│   ├── model.py          # Incident data model + SigNoz parser
│   ├── store.py          # SQLite incident store
│   ├── lineage.py        # AgentLineage graph builder + query
│   ├── revoker.py        # Credential revocation orchestrator
│   └── telemetry.py      # OTLP/HTTP trace export
├── frontend/
│   └── index.html        # Professional landing page + docs
├── tests/                # 102 unit tests
├── deploy/               # Docker, SigNoz dashboard, alerts
├── demo/                 # Runaway agent simulation
└── docs/                 # Architecture, judging matrix
```

## Demo

Run the interactive demo:
```bash
# Terminal 1: Start Sentinel
python -m sentinel --port 8090 --webhook-secret test --dry-run

# Terminal 2: Simulate runaway agent
python demo/runaway_agent.py --threshold 8

# Terminal 3: Query lineage
curl http://localhost:8090/agent-lineage
```

## Safety Guarantees

- **Reversible only** — quarantine is reversible; no destructive actions
- **Dry-run default** — `--dry-run` logs actions without revoking
- **HMAC-authenticated** — all webhooks signed with replay protection
- **Idempotent** — duplicate alerts trigger at most one quarantine
- **Audit trail** — every action recorded in SQLite with immutable timestamps
- **No secrets in logs** — credentials hashed in telemetry, never logged
- **Zero dependencies** — Python stdlib only, no pip install needed

## Frontend

Professional landing page with:
- Scroll-driven animations (IntersectionObserver, CSS 3D perspective)
- Detailed documentation (Installation, Config, API, Architecture, Troubleshooting)
- Anti-slop design (General Sans + Cabinet Grotesk + IBM Plex Mono, no Inter/Roboto)

## Running Tests

```bash
cd tests && npm install && npx vitest run
# 102 tests passing
```

## License

MIT
