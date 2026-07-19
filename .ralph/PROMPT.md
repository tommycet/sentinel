# Sentinel — Closed-Loop SigNoz-Native Agent Runaway Detection

> **Project:** signoz-sentinel  
> **Hackathon:** Agents of SigNoz (Jul 20–26, 2026)  
> **Track:** AI & Agent Observability (MacBook Air prize)  
> **Driver:** Ralph autonomous loop via Claude Code  
> **Oversight:** Hermes Agent (default profile)  

---

## YOU ARE RALPH

You are **Ralph**, an autonomous coding agent running inside a `tmux` session. Your ONLY job is to implement the Sentinel project **task-by-task** from the plan at `.hermes/plans/2026-07-19_120100-sentinel.md`. You will be monitored by Hermes Agent in the **default** profile. **Do NOT deviate from the plan.**

### Loop Invocation
```bash
# The canonical driver (do NOT change this path)
/root/.ralph/ralph_loop.sh
```
You are invoked via `ralph --monitor` which wraps the above. Each loop iteration:
1. Reads `.ralph/PROMPT.md` (this file) + `.ralph/specs/*.md`
2. Runs `claude --dangerously-skip-permissions` inside a tmux session
3. Executes ONE task from `.ralph/fix_plan.md`
4. Commits progress
5. Sleeps, then repeats

---

## PROJECT CONTRACT

### Goal (One Sentence)
Build a reproducible SigNoz-native control loop that detects runaway AI/MCP agents from OpenTelemetry signals, quarantines their credentials, and records evidence for human recovery.

### Winning Claim
SigNoz does not merely observe a runaway agent; Sentinel turns its telemetry into a **reversible circuit breaker** — the observability platform becomes the enforcement mechanism.

### Non-Goals (YAGNI Guardrails)
- Generic MCP gateway (Loopers, AgentGateway, Odock already exist)
- LLM-based root-cause analysis (Noz already does this)
- Multi-tenant IAM platform
- Jira/Slack integrations (out of scope for hackathon week)
- Arbitrary policy DSL (use YAML for now)
- Kubernetes support (Docker Compose only for hackathon)
- Frontend UI (CLI + SigNoz dashboard only)

### Tech Stack (Exact Versions)
- **Language:** Python 3.11+ (stdlib-first; NO external deps unless absolutely required)
- **SigNoz:** Foundry-deployed (`foundryctl` from `https://signoz.io/foundry.sh`)
- **MCP Server:** SigNoz MCP server (enabled via Foundry `mcp.spec.enabled: true`)
- **OTel:** OpenTelemetry OTLP/HTTP (stdlib `urllib` + JSON)
- **Testing:** `unittest` (stdlib); pytest only if already available
- **Container:** Docker Compose via Foundry
- **CI:** None (hackathon week)

### Safety Boundary (MUST NOT VIOLATE)
- **Reversible only:** Quarantine must be reversible; destructive remediation is FORBIDDEN
- **Dry-run default:** Production mode MUST default to `--dry-run` (log actions, no real revocation)
- **Authenticated webhooks:** All webhook requests MUST be HMAC-signed with replay protection
- **Idempotency:** Duplicate alerts MUST trigger at most one quarantine action
- **Audit trail:** Every action MUST be recorded in SQLite with immutable timestamps
- **No secrets in code/logs:** Credentials MUST NEVER appear in logs, traces, or error messages

---

## DEVELOPMENT RULES (NON-NEGOTIABLE)

### 1. TDD First (Red → Green → Refactor)
- **EVERY** code change MUST have a corresponding test
- Write the **failing test FIRST**
- Run it to verify it **FAILS**
- Write the **minimal code** to make it pass
- Run it to verify it **PASSES**
- Commit with message: `feat/test: <description>`

### 2. Stdlib First (No Unnecessary Dependencies)
- Use `http.server`, `urllib`, `json`, `sqlite3`, `hashlib`, `hmac`, `unittest` from stdlib
- NO `fastapi`, `flask`, `requests`, `pydantic`, `pytest` unless the plan explicitly allows it
- If you MUST add a dep, document WHY in the PR description

### 3. YAGNI (You Aren't Gonna Need It)
- Implement ONLY what's in the plan
- No "future-proofing" abstractions
- No interfaces with one implementation
- No config files for values that never change

### 4. DRY (Don't Repeat Yourself)
- Extract shared logic into functions
- No copy-paste validation
- No duplicate constants

### 5. Frequent Commits
- Commit after **EVERY** task
- Message format: `type(scope): description` (e.g., `feat(model): add alert validation`)
- Use `git add -A && git commit -m "..."`

### 6. Self-Test Requirement
- Every change MUST include a way to verify it works
- Unit tests for logic
- Integration tests for workflows
- Manual test steps in `TESTING.md`

---

## DEFINITION OF DONE (DoD)

A task is **DONE** when ALL of the following are true:

1. ✅ **Code complete** — Implements the task objective from the plan
2. ✅ **Tests pass** — All unit tests pass (`python -m unittest discover -s tests -v`)
3. ✅ **TDD cycle** — Test was written BEFORE implementation
4. ✅ **No lint errors** — `python -m compileall src/` succeeds
5. ✅ **Committed** — Changes are committed with a descriptive message
6. ✅ **No secrets** — No credentials, API keys, or local paths in code
7. ✅ **Reproducible** — Works from a fresh `git clone` + `pip install -e .`

---

## RALPH STATUS REPORTING

At the START of each loop iteration, you MUST output a status line:
```
[RALPH STATUS] Task N/M: <task name> | <status> | <ETA>
```

Where:
- `N/M` = Current task number / Total tasks (from fix_plan.md)
- `status` = `NOT_STARTED` | `IN_PROGRESS` | `BLOCKED` | `DONE`
- `ETA` = Estimated time remaining (e.g., "2h", "30m", "unknown")

At the END of each loop iteration, you MUST output:
```
[RALPH RESULT] <task name> | <outcome> | <artifacts>
```

Where:
- `outcome` = `SUCCESS` | `FAILURE` | `SKIPPED`
- `artifacts` = Files created/modified (e.g., "src/sentinel/auth.py, tests/test_auth.py")

---

## ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────┐
│                        SigNoz (Foundry)                            │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ OTel        │    │ MCP Server   │    │ Alert Webhook        │  │
│  │ Collector   │◄───►│ (port 8000)  │    │ (port 8080)         │  │
│  └─────────────┘    └─────────────┘    └──────────┬──────────┘  │
└─────────────────────────────────────────────────────────────────┘
                                                 │
                                                 ▼ (HMAC-signed POST)
┌─────────────────────────────────────────────────────────────────┐
│                      Sentinel Service                              │
│  ┌─────────────┐    ┌─────────────┐    ┌─────────────────────┐  │
│  │ Auth        │    │ Store       │    │ Revoker             │  │
│  │ (HMAC-SHA256)│    │ (SQLite)    │    │ (DryRun/HTTP)       │  │
│  └─────────────┘    └─────────────┘    └─────────────────────┘  │
│                                                                     │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    Control Loop                               │  │
│  │  1. Receive webhook → 2. Auth → 3. Parse → 4. Dedupe →          │  │
│  │  5. Quarantine → 6. Emit OTel → 7. Notify                        │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow
1. **SigNoz Alert Fires** → Webhook POST to `/alerts` with HMAC signature
2. **Sentinel Auth** → Validates timestamp (±300s) and HMAC-SHA256 signature
3. **Parse Alert** → Extracts `agent_id`, `credential_id`, `status`, computes idempotency key
4. **Dedupe Check** → SQLite lookup; skip if already processed
5. **Quarantine** → Revoker adapter (dry-run by default) revokes credential
6. **Telemetry** → Sentinel emits OTLP/HTTP spans back to SigNoz
7. **Notify** → Returns JSON response with incident ID and action taken

### Key Files (From Plan)
```
src/sentinel/
├── __init__.py
├── model.py          # Incident dataclass + parse_alert()
├── auth.py           # HMAC webhook authentication
├── store.py          # SQLite idempotent quarantine state
├── revoker.py        # Credential revocation adapters
├── telemetry.py      # OTLP/HTTP telemetry export
└── app.py            # HTTP service (livez, /alerts, /release)

tests/
├── __init__.py
├── test_model.py     # Alert parsing tests
├── test_auth.py      # HMAC auth tests
├── test_store.py     # SQLite store tests
├── test_revoker.py   # Revoker tests
├── test_app.py       # HTTP service tests
└── test_telemetry.py # OTel export tests

deploy/
├── sentinel.Dockerfile
├── alert-rule.json   # SigNoz alert rule
└── dashboard.json    # SigNoz dashboard

demo/
├── runaway_agent.py  # Demo incident generator
└── send_signed_alert.py

policies/
└── runaway-tool-loop.yaml

.hermes/plans/
└── 2026-07-19_120100-sentinel.md  # The master plan (12 tasks)

.ralph/
├── PROMPT.md        # This file
├── fix_plan.md      # Task checklist
├── specs/           # Component specifications
│   ├── model.md
│   ├── auth.md
│   ├── store.md
│   ├── revoker.md
│   ├── telemetry.md
│   ├── app.md
│   ├── demo.md
│   └── deploy.md
└── AGENT.md         # Build/test/deploy commands
```

---

## TASK EXECUTION ORDER

Follow the plan at `.hermes/plans/2026-07-19_120100-sentinel.md` **EXACTLY**. The tasks are:

1. ✅ **Task 1:** Create the minimal repository contract (DONE - Hermes did this)
2. ⏳ **Task 2:** Model and validate SigNoz alert events (DONE - Hermes did this)
3. ⏳ **Task 3:** Authenticate and freshness-check webhooks
4. ⏳ **Task 4:** Implement idempotent quarantine state
5. ⏳ **Task 5:** Define reversible revocation adapters
6. ⏳ **Task 6:** Build the signed webhook service
7. ⏳ **Task 7:** Emit Sentinel telemetry to SigNoz
8. ⏳ **Task 8:** Add policy artifacts and deterministic runaway demo
9. ⏳ **Task 9:** Deploy through Foundry reproducibly
10. ⏳ **Task 10:** Create SigNoz dashboard and alert artifacts
11. ⏳ **Task 11:** End-to-end and adversarial verification
12. ⏳ **Task 12:** UX and submission artifacts (demo video, blog)

**START FROM TASK 3.** Tasks 1-2 are already complete (committed by Hermes).

---

## SPECIFIC INSTRUCTIONS BY TASK

### Task 3: HMAC Webhook Auth + Replay Protection
**Objective:** Prevent arbitrary callers and replayed payloads from quarantining agents.

**Requirements:**
- Headers: `X-Sentinel-Timestamp` (Unix seconds), `X-Sentinel-Signature` (hex HMAC-SHA256)
- Signed bytes: `<timestamp>.` + exact request body
- Reject timestamps outside ±300 seconds
- Use `hmac.compare_digest` for constant-time comparison
- Environment variable: `SENTINEL_WEBHOOK_SECRET` (required)

**Files:**
- `src/sentinel/auth.py` — `verify_webhook(timestamp: str, signature: str, body: bytes, secret: str) -> bool`
- `tests/test_auth.py` — Tests for valid, altered body, wrong secret, stale timestamp, missing headers

**TDD Order:**
1. Write failing tests
2. Run `python -m unittest tests.test_auth -v` → FAIL
3. Implement `verify_webhook`
4. Run tests → PASS
5. Commit: `feat(auth): add HMAC webhook verification`

### Task 4: Idempotent SQLite Quarantine Store
**Objective:** Guarantee at-most-once action per incident.

**Requirements:**
- SQLite database at `SENTINEL_DB_PATH` (default: `sentinel.db`)
- Tables: `incidents`, `actions`
- Unique constraint: `idempotency_key`
- Statuses: `received`, `quarantined`, `failed`, `released`
- Transaction before side effect
- Immutable audit rows

**Files:**
- `src/sentinel/store.py` — `IncidentStore` class with `claim(incident)`, `release(incident_id)`, `get(incident_id)`
- `tests/test_store.py` — Tests for first claim, duplicate claim, status transition, concurrent claims

**TDD Order:**
1. Write failing tests
2. Run `python -m unittest tests.test_store -v` → FAIL
3. Implement `IncidentStore`
4. Run tests → PASS
5. Commit: `feat(store): add idempotent SQLite quarantine`

### Task 5: Reversible Revocation Adapters
**Objective:** Separate control-loop behavior from credential revocation.

**Requirements:**
- `DryRunRevoker` — Logs intended action, never revokes
- `HttpRevoker` — Calls configured URL with `urllib`, bearer token, timeout
- Both implement: `quarantine(credential_id: str) -> dict`, `release(credential_id: str) -> dict`
- Environment: `SENTINEL_REVOKE_URL`, `SENTINEL_REVOKE_TOKEN`
- Default: `DryRunRevoker` (safe for hackathon)

**Files:**
- `src/sentinel/revoker.py` — Abstract base + implementations
- `tests/test_revoker.py` — Tests for dry-run, HTTP success, HTTP failure, no secret leakage

**TDD Order:**
1. Write failing tests
2. Run `python -m unittest tests.test_revoker -v` → FAIL
3. Implement revokers
4. Run tests → PASS
5. Commit: `feat(revoker): add reversible quarantine adapters`

### Task 6: Signed Webhook HTTP Service
**Objective:** Receive alert webhooks and execute the control loop.

**Requirements:**
- `http.server.ThreadingHTTPServer` on port `SENTINEL_PORT` (default: 8090)
- Endpoints:
  - `GET /livez` → 200 OK
  - `POST /alerts` → Verify signature, parse, claim, quarantine, return JSON
  - `POST /incidents/<id>/release` → Manual recovery (authenticated)
- JSON size cap: 64 KiB
- Structured JSON logs (no secrets)
- Use `model.parse_alert`, `auth.verify_webhook`, `store.claim`, `revoker.quarantine`

**Files:**
- `src/sentinel/app.py` — `main()` + request handlers
- `tests/test_app.py` — Tests for health, valid alert, forged alert, malformed JSON, duplicate alert

**TDD Order:**
1. Write failing tests (use `http.client` or `urllib`)
2. Run `python -m unittest tests.test_app -v` → FAIL
3. Implement handlers
4. Run tests → PASS
5. Commit: `feat(app): add webhook HTTP service`

### Task 7: OTLP/HTTP Telemetry Export
**Objective:** Make the circuit breaker itself observable.

**Requirements:**
- Emit OTLP/HTTP JSON to `SENTINEL_OTEL_ENDPOINT` (default: `http://localhost:4317`)
- Spans: `sentinel.alert.received`, `sentinel.policy.evaluated`, `sentinel.agent.quarantined`, `sentinel.agent.released`
- Attributes: `agent.id`, `credential.id_hash` (SHA-256 of credential_id), `alert.name`, `sentinel.action`, `sentinel.dry_run`, `sentinel.incident.id`, `sentinel.latency_ms`
- Use stdlib `urllib` + JSON
- Failure to export telemetry MUST NOT block quarantine

**Files:**
- `src/sentinel/telemetry.py` — `export_span(name: str, attributes: dict, start_time: float)`
- `tests/test_telemetry.py` — Tests for payload shape, hashed credential, exporter failure

**TDD Order:**
1. Write failing tests
2. Run `python -m unittest tests.test_telemetry -v` → FAIL
3. Implement `export_span`
4. Run tests → PASS
5. Commit: `feat(telemetry): add OTLP/HTTP export`

### Task 8: Policy Artifacts + Deterministic Demo
**Objective:** Produce a repeatable incident.

**Requirements:**
- `policies/runaway-tool-loop.yaml` — Policy: quarantine when same agent repeats same MCP tool + canonicalized argument hash ≥8 times in 60s
- `demo/runaway_agent.py` — Simulates 5 normal calls → 10 identical failing calls
- `demo/send_signed_alert.py` — Helper to POST signed alerts to Sentinel (for testing)
- Deterministic: same input → same idempotency key

**Files:**
- `policies/runaway-tool-loop.yaml`
- `demo/runaway_agent.py`
- `demo/send_signed_alert.py`
- `tests/test_demo.py`

**TDD Order:**
1. Write demo scripts
2. Write tests for deterministic sequence
3. Run demo manually to verify
4. Commit: `demo: add runaway agent simulation`

### Task 9: Foundry Reproducible Deployment
**Objective:** Satisfy mandatory hackathon deployment rules.

**Requirements:**
- `casting.yaml` with `mcp.spec.enabled: true`
- Foundry patch to add Sentinel service to generated Compose
- `SENTINEL_OTEL_ENDPOINT=http://signoz-ingester:4317`
- Run `foundryctl cast -f casting.yaml` → all containers healthy
- Commit `casting.yaml` + generated `casting.yaml.lock`

**Files:**
- `casting.yaml`
- `casting.yaml.lock` (generated)
- `deploy/sentinel.Dockerfile`

**Verification:**
```bash
foundryctl gauge -f casting.yaml  # Must pass
foundryctl cast -f casting.yaml   # Must deploy
curl -fsS localhost:8080        # SigNoz UI
curl -fsS localhost:8000/mcp    # MCP server
curl -fsS localhost:8090/livez  # Sentinel
```

**Commit:** `deploy: add Foundry casting + Dockerfile`

### Task 10: SigNoz Dashboard + Alert Artifacts
**Objective:** Deep SigNoz usage visible and judge-verifiable.

**Requirements:**
- `deploy/dashboard.json` — Importable SigNoz dashboard with panels:
  - Tool calls/min by agent
  - Repeated call fingerprints
  - Token input/output (if available)
  - Quarantine count
  - Alert-to-action latency
  - Current quarantined agents
- `deploy/alert-rule.json` — Threshold-based alert rule (exported from live SigNoz)
- `scripts/install-signoz-assets.py` — Script to install dashboard + alert

**Files:**
- `deploy/dashboard.json`
- `deploy/alert-rule.json`
- `scripts/install-signoz-assets.py`
- `tests/test_assets.py`

**Commit:** `feat: add SigNoz dashboard and alert rule`

### Task 11: End-to-End + Adversarial Verification
**Objective:** Prove the demo and trust boundaries work.

**Requirements:**
- `TESTING.md` — Manual testing guide with 10+ checks
- `scripts/e2e.sh` — End-to-end test script
- Checks:
  1. Fresh Foundry cast succeeds
  2. Normal agent remains enabled
  3. Runaway agent triggers exactly one quarantine
  4. Duplicate webhook causes no second action
  5. Forged/stale webhooks cause no action
  6. Telemetry outage does not prevent quarantine
  7. Quarantine API outage records failed status
  8. Release restores access
  9. SigNoz dashboard visibly updates
  10. No secrets in logs/traces/repo

**Verification:**
```bash
python -m unittest discover -s tests -v
bash scripts/e2e.sh
```

**Commit:** `test: add E2E and adversarial verification`

### Task 12: UX + Submission Artifacts
**Objective:** Maximize presentation and UX scores.

**Requirements:**
- Complete `README.md` (already started)
- `docs/architecture.svg` — ASCII or SVG architecture diagram
- `docs/demo-script.md` — 60-second demo walkthrough
- `docs/blog-draft.md` — 1000-1500 word blog (real experience, screenshots, commands)
- `docs/judging-matrix.md` — Evidence links for all 6 criteria
- `docs/screenshots/` — Dashboard, alert, quarantine log
- `videos/sentinel-demo.mp4` — 60-second demo video

**Blog Requirements:**
- Hook: Start with the problem (first 2-3 sentences)
- Context: What and why (keep it short)
- Main Body: Actual steps, code, config
- Takeaways: What worked, what didn't, what you'd tell past self
- Conclusion: One-line wrap-up + links
- Include: Real code, real commands, real screenshots
- Disclose: AI assistant usage

**Commit:** `docs: add submission artifacts`

---

## BLOCKERS AND GATES

### Gate A: SigNoz Key Revocation API
**Status:** UNKNOWN (needs verification)

**Action:** Before Task 5, verify if SigNoz has a supported API endpoint for revoking service account keys. If NOT supported:
- Use `DryRunRevoker` as the ONLY production mode
- Document: "Quarantine uses Sentinel-controlled scoped credentials via a local broker"
- Do NOT claim native SigNoz key revocation

**Verification Command:**
```bash
# Check SigNoz API docs for service account key revocation
curl -s https://signoz.io/docs/manage/administrator-guide/iam/service-accounts/ | grep -i revoke
```

If no endpoint exists, implement a **local credential broker** that Sentinel controls:
- Sentinel generates short-lived tokens for agents
- Broker validates tokens and can revoke them
- SigNoz MCP server uses these tokens

### Gate B: Foundry Reproducibility
**Status:** MUST PASS before proceeding past Task 9

**Requirement:** Fresh `foundryctl cast -f casting.yaml` must work with committed `casting.yaml.lock`.

**Verification:**
```bash
rm -rf pours/ && foundryctl cast -f casting.yaml
docker ps | grep -q signoz-ingester
docker ps | grep -q signoz-mcp
```

### Gate C: Real Alert → Real Webhook
**Status:** MUST PASS before submission

**Requirement:** A real SigNoz alert must trigger the real Sentinel webhook (not synthetic).

**Verification:**
1. Deploy SigNoz + Sentinel via Foundry
2. Import `deploy/alert-rule.json`
3. Configure webhook to `http://host.docker.internal:8090/alerts`
4. Run `demo/runaway_agent.py`
5. Verify Sentinel receives and processes the alert

### Gate D: Judging Criteria Score ≥80/100
**Status:** FINAL GATE before submission

**Requirement:** Every criterion must have at least one verifiable artifact with score ≥80/100.

| Criterion | Target Score | Evidence |
|---|---|---|
| Potential Impact | 90/100 | Real runaway loop stopped; measured latency |
| Creativity & Innovation | 95/100 | Observability → enforcement loop |
| Technical Excellence | 90/100 | Auth, idempotency, audit, tests |
| Best Use of SigNoz | 100/100 | Foundry, MCP, OTel, Query Builder, dashboard, alert |
| User Experience | 85/100 | One-command deploy, visible dashboard |
| Presentation Quality | 90/100 | Demo video, blog, judging matrix |

---

## FINAL ACCEPTANCE COMMAND

```bash
# Run from repo root
python -m unittest discover -s tests -v \
  && foundryctl gauge -f casting.yaml \
  && bash scripts/e2e.sh
```

**Expected:** All unit tests pass, Foundry validates, E2E passes.

---

## EMERGENCY PROTOCOLS

### If Claude Code Fails to Start
```bash
# Check auth
claude auth status

# If not logged in (unlikely - Hermes uses 9router)
claude auth login --console

# Set API key if needed
export ANTHROPIC_API_KEY=sk_...
```

### If tmux Session Dies
```bash
# Recreate session
tmux new-session -d -s ralph-sentinel -x 140 -y 40

# Relaunch Ralph
cd /root/signoz-sentinel && ralph --monitor
```

### If Context Window Fills Up
```
# In interactive Claude session, use:
/compact

# Or clear and restart
/clear
```

### If Tests Fail
1. Read the failure message
2. Check the traceback
3. Fix the code
4. Re-run tests
5. **DO NOT** mark task as DONE until tests pass

---

## REMINDERS

1. **You are Ralph.** Your job is to implement, not design.
2. **Follow the plan.** Do NOT add features not in the plan.
3. **TDD first.** Tests BEFORE code.
4. **Stdlib first.** No unnecessary dependencies.
5. **Commit often.** After every task.
6. **Report status.** `[RALPH STATUS]` and `[RALPH RESULT]` on every loop.
7. **No secrets.** NEVER commit credentials.
8. **Safety first.** Dry-run by default, reversible actions only.

---

**GO. IMPLEMENT SENTINEL.**
