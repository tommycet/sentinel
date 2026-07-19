# Sentinel — Closed-Loop SigNoz-Native Agent Runaway Detection

**SigNoz does not merely observe a runaway agent; Sentinel turns its telemetry into a reversible circuit breaker — the observability platform becomes the enforcement mechanism.**

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## Overview

Sentinel is a deterministic control loop that detects runaway AI/MCP agents from OpenTelemetry signals emitted to SigNoz, quarantines their credentials, and records evidence for human recovery. Built entirely with Python stdlib — one `pip install`, one `docker compose up`.

## Architecture

```
SigNoz (Foundry)           Sentinel Service
┌──────────────────┐      ┌─────────────────────────────┐
│ OTel Collector ◄──┼──────┤ Auth (HMAC-SHA256)          │
│ MCP Server       │      │ Store (SQLite, idempotent)  │
│ Alert Webhook ───┼──POST┤ Revoker (dry-run default)   │
└──────────────────┘ HMAC  │ Telemetry (OTLP/HTTP)       │
                           │ Control Loop: Receive →     │
                           │  Auth → Parse → Dedupe →    │
                           │  Quarantine → Emit → Notify │
                           └─────────────────────────────┘
```

## Quick Start

```bash
git clone https://github.com/your-org/signoz-sentinel
cd signoz-sentinel
pip install -e .
PYTHONPATH=src:. python -m unittest discover -s tests -v   # 93 tests

# Run the demo
PYTHONPATH=src:. python demo/runaway_agent.py --threshold 8
```

## Deploy

```bash
foundryctl gauge -f casting.yaml        # validate
foundryctl forge -f casting.yaml         # generate compose
docker compose -f pours/deployment/compose.yaml up -d
python3 scripts/install-signoz-assets.py  # import dashboard + alert
```

## Project Structure

| Path | Purpose |
|------|---------|
| `src/sentinel/` | Core service (model, auth, store, revoker, telemetry, app) |
| `tests/` | 93 unit tests |
| `deploy/` | Dockerfile, dashboard.json, alert-rule.json |
| `demo/` | Runaway agent simulation, signed alert sender |
| `policies/` | Detection policy YAML |
| `casting.yaml` | Foundry deployment config |
| `docs/` | Architecture diagram, demo script, judging matrix |

## Safety Guarantees

- **Reversible only** — quarantine is reversible; no destructive actions
- **Dry-run default** — `--dry-run` logs actions without revoking
- **HMAC-authenticated** — all webhooks signed with replay protection
- **Idempotent** — duplicate alerts trigger at most one quarantine
- **Audit trail** — every action recorded in SQLite with immutable timestamps
- **No secrets in logs** — credentials hashed in telemetry, never logged

## License

MIT