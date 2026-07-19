# Sentinel

> **AI Assistant Disclosure:** This project was designed and built with the assistance of Hermes Agent. All code, documentation, and assets were authored or reviewed by humans.

**Sentinel** is a closed-loop, SigNoz-native control system that detects runaway AI/MCP agents from OpenTelemetry signals, quarantines their credentials, and records forensic evidence for human recovery.

## Problem

AI agents can enter infinite tool-call loops, exhaust token budgets, or cascade failures across services. Traditional monitoring flags infrastructure-level signals (CPU, HTTP 5xx) too late. SigNoz already ingests agent-specific telemetry (traces, metrics, logs, token costs), but that visibility is passive. When an incident fires at 3 AM, the on-call engineer still has to wake up and act.

## Claim

Sentinel turns SigNoz's observability into a reversible circuit breaker. It listens to SigNoz alerts, validates and deduplicates them, quarantines the offending agent's credentials, and emits its own control-loop telemetry back into SigNoz — all without adding a new proxy or gateway layer.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        SigNoz (Foundry)                         │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  OTel       │    │ MCP Server  │    │  Alert Webhook   │  │
│  │  Collector  │◄───►│ (port 8000) │    │ (port 8080)     │  │
│  └─────────────┘    └─────────────┘    └────────┬────────┘  │
└─────────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼
┌─────────────────────────────────────────────────────────────┐
│                      Sentinel Service                           │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────┐  │
│  │  Auth       │    │  Store      │    │  Revoker        │  │
│  │  (HMAC)     │    │  (SQLite)   │    │  (DryRun/HTTP)  │  │
│  └─────────────┘    └─────────────┘    └─────────────────┘  │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │                    Control Loop                            │  │
│  │  Alert → Validate → Dedupe → Quarantine → Emit Telemetry    │  │
│  └─────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

- **SigNoz** is deployed via Foundry (`casting.yaml`).
- **SigNoz MCP Server** exposes metrics, traces, logs, alerts to AI clients on port 8000.
- **SigNoz Alert Webhook** fires when a configured rule triggers (e.g., repeated MCP tool calls).
- **Sentinel** receives the webhook, validates it, deduplicates it, quarantines the agent's credential, and emits its own OTel telemetry back to SigNoz.

## Quickstart

### Prerequisites

- Docker + Docker Compose
- `foundryctl` (installed via `curl -fsSL https://signoz.io/foundry.sh | bash`)
- Python 3.11+

### 1. Deploy SigNoz with MCP enabled

```bash
cd signoz-sentinel
foundryctl cast -f casting.yaml
```

Wait for all containers to report `healthy`. SigNoz UI will be available at `http://localhost:8080`.

### 2. Configure a SigNoz Alert Rule

Import `deploy/alert-rule.json` via the SigNoz UI (Alerts → Create → Import JSON).

The rule should target a metric or trace attribute that indicates runaway behavior (e.g., repeated MCP tool calls).

### 3. Configure the Alert Webhook

In SigNoz UI:
1. Navigate to **Alerts → Notification Policies**.
2. Add a new **Webhook** notification channel.
3. Set the URL to `http://host.docker.internal:8090/alerts` (or the appropriate host/port for your Sentinel service).
4. Add a custom header: `X-Sentinel-Signature` with a shared secret (configured in Sentinel via `SENTINEL_WEBHOOK_SECRET`).

### 4. Start Sentinel

```bash
# From a new terminal
cd signoz-sentinel
pip install -e .
sentinel --port 8090 --dry-run
```

### 5. Trigger a Demo Incident

Run the demo script to simulate a runaway agent:

```bash
python demo/runaway_agent.py
```

Observe:
- SigNoz dashboard updates with the incident.
- Sentinel receives the alert, quarantines the agent, and logs the action.
- The agent's subsequent tool calls are blocked.

### 6. Recover the Agent

```bash
# Manually release the quarantined agent
curl -X POST http://localhost:8090/incidents/<incident-id>/release \
  -H "X-Sentinel-Signature: <signature>"
```

## Safety Model

- **Dry-run by default:** Sentinel starts in dry-run mode (`--dry-run`), where it logs intended actions without revoking credentials.
- **Reversible actions:** All quarantine actions can be manually released via the `/incidents/<id>/release` endpoint.
- **Idempotency:** Duplicate alerts for the same incident trigger at most one quarantine action.
- **Allowlist:** Only credential IDs in the configured allowlist (`SENTINEL_ALLOWED_CREDENTIALS`) can be quarantined.
- **Audit trail:** All actions are recorded in a SQLite database (`sentinel.db`) with immutable timestamps.
- **No destructive actions:** Sentinel does not delete or modify data; it only revokes access temporarily.

## Configuration

| Environment Variable | Description | Default |
|---|---|---|
| `SENTINEL_PORT` | Port for the Sentinel HTTP server | `8090` |
| `SENTINEL_WEBHOOK_SECRET` | Shared secret for HMAC-signing webhook requests | *Required* |
| `SENTINEL_ALLOWED_CREDENTIALS` | Comma-separated list of allowed credential IDs | `""` (all) |
| `SENTINEL_DRY_RUN` | If `true`, log actions without revoking credentials | `true` |
| `SENTINEL_DB_PATH` | Path to the SQLite database | `sentinel.db` |
| `SENTINEL_OTEL_ENDPOINT` | OTLP/HTTP endpoint for Sentinel's own telemetry | `http://localhost:4317` |
| `SENTINEL_REVOKE_URL` | URL for revoking credentials (if supported by SigNoz) | `""` (dry-run) |

## Project Structure

```
signoz-sentinel/
├── casting.yaml              # Foundry casting file
├── casting.yaml.lock        # Generated lockfile (committed)
├── pyproject.toml            # Python project config
├── README.md                 # This file
├── LICENSE                   # MIT License
├── src/
│   └── sentinel/
│       ├── __init__.py
│       ├── model.py          # Alert validation and modeling
│       ├── auth.py           # Webhook authentication
│       ├── store.py          # Idempotent quarantine state
│       ├── revoker.py        # Credential revocation adapters
│       ├── telemetry.py      # OTel telemetry export
│       └── app.py            # HTTP service
├── tests/                    # Unit and integration tests
├── demo/
│   ├── runaway_agent.py      # Demo incident generator
│   └── send_signed_alert.py  # Helper to send test alerts
├── deploy/
│   ├── alert-rule.json       # SigNoz alert rule
│   └── dashboard.json        # SigNoz dashboard
├── policies/
│   └── runaway-tool-loop.yaml # Detection policy
├── docs/
│   ├── architecture.svg      # Architecture diagram
│   ├── demo-script.md        # Demo walkthrough
│   └── blog-draft.md         # Blog post draft
└── videos/
    └── sentinel-demo.mp4     # Demo video
```

## Development

### Running Tests

```bash
python -m unittest discover -s tests -v
```

### Building the Docker Image

```bash
# Build the Sentinel service image
docker build -t sentinel:latest -f deploy/sentinel.Dockerfile .

# Or use the Foundry-generated Compose stack
foundryctl cast -f casting.yaml
```

### Linting

```bash
python -m compileall src/
```

## Hackathon Submission

This project is built for the **Agents of SigNoz** hackathon (July 20–26, 2026).

### Judging Criteria Coverage

| Criterion | Evidence |
|---|---|
| **Potential Impact** | Real runaway loop stopped; measured blast radius and latency |
| **Creativity & Innovation** | Observability becomes reversible enforcement; no LLM wrapper |
| **Technical Excellence** | Auth, replay defense, idempotency, audit trail, reversible actions, E2E tests |
| **Best Use of SigNoz** | Foundry, MCP telemetry, OTel traces, Query Builder, dashboard, alert, webhook |
| **User Experience** | One-command deployment, visible dashboard, dry-run, release workflow |
| **Presentation Quality** | 60-second demo, honest blog, architecture, judging matrix |

### Submission Checklist

- [ ] All judging criteria have at least one deliverable
- [ ] Automated tests pass (100%)
- [ ] Manual testing guide exists (`TESTING.md`)
- [ ] Demo video exists and shows the key workflow
- [ ] UI is visually polished (verified via vision or screenshot)
- [ ] README explains the project, how to run it, and how to verify it
- [ ] Blog post drafted (`docs/blog-draft.md`)
- [ ] All configuration files are valid JSON/YAML
- [ ] No hardcoded secrets or local paths
- [ ] Project builds cleanly from fresh clone

## License

MIT License — see [LICENSE](LICENSE).
