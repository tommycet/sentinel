# AGENT.md — Sentinel Build & Test Commands

## Build
```bash
# Install in dev mode
cd /root/signoz-sentinel
pip install -e .
```

## Test
```bash
# Run all tests
python -m unittest discover -s tests -v

# Run specific test file
python -m unittest tests.test_model -v
python -m unittest tests.test_auth -v
python -m unittest tests.test_store -v
python -m unittest tests.test_revoker -v
python -m unittest tests.test_app -v
python -m unittest tests.test_telemetry -v

# Lint check (no external linter - just compile check)
python -m compileall src/
```

## Build & Run
```bash
# Run Sentinel directly (from source)
sentinel --port 8090 --dry-run --secret test-secret

# Or via Python module
python -m sentinel.app --port 8090 --dry-run
```

## Docker
```bash
# Build
docker build -t sentinel:latest -f deploy/sentinel.Dockerfile .

# Run (for testing without Foundry)
docker run -d \
  --name sentinel \
  -p 8090:8090 \
  -e SENTINEL_WEBHOOK_SECRET=test-secret \
  -e SENTINEL_DRY_RUN=true \
  sentinel:latest
```

## Foundry Deployment
```bash
# Validate casting
foundryctl gauge -f casting.yaml

# Deploy full stack
foundryctl cast -f casting.yaml

# Verify
curl -fsS http://localhost:8090/livez
```

## Git Workflow
```bash
# Commit after every task
git add -A
git commit -m "type(scope): description"

# Push (if remote configured)
git push origin main
```

## Quality Standards
- **TDD first.** Write the failing test BEFORE the implementation code.
- **Stdlib only.** No FastAPI, Flask, Requests, Pydantic, pytest unless explicitly allowed.
- **C@n. Read coverage via Python's built-in coverage tools.** Target is not a specific percentage but every edge case in the spec.
- **No secrets in code.** Use environment variables for all secrets.
- **Commit early, commit often.** After every task.
- **Dry-run default.** Sentinel MUST default to safe mode.
