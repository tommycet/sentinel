# Sentinel Fix Plan

## Build Order (12 Tasks)

### Phase 1: Core Infrastructure
- [x] **Task 1:** Project initialization (pyproject.toml, .gitignore, LICENSE, package structure)
- [x] **Task 2:** Alert model and validation (src/sentinel/model.py + tests)
- [x] **Task 3:** HMAC webhook authentication + replay protection (src/sentinel/auth.py + tests)
- [x] **Task 4:** Idempotent SQLite quarantine store (src/sentinel/store.py + tests)
- [x] **Task 5:** Reversible revocation adapters (src/sentinel/revoker.py + tests)

### Phase 2: Service & Telemetry
- [x] **Task 6:** Signed webhook HTTP service (src/sentinel/app.py + tests)
- [x] **Task 7:** OTLP/HTTP telemetry export (src/sentinel/telemetry.py + tests)

### Phase 3: Demo & Policy
- [x] **Task 8:** Policy artifacts + deterministic runaway demo (demo/ + policies/)

### Phase 4: Deployment
- [ ] **Task 9:** Foundry reproducible deployment (casting.yaml + Dockerfile)
- [ ] **Task 10:** SigNoz dashboard + alert artifacts (deploy/)

### Phase 5: Verification & Polish
- [ ] **Task 11:** E2E + adversarial verification (TESTING.md + e2e.sh)
- [ ] **Task 12:** UX + submission assets (blog, video, screenshots, judging matrix)

## Gates
- [ ] **Gate A:** Verify SigNoz key revocation API exists
- [ ] **Gate B:** Fresh Foundry deployment works with committed lockfile
- [ ] **Gate C:** Real SigNoz alert triggers real Sentinel webhook
- [ ] **Gate D:** All 6 judging criteria scored ≥80/100 with evidence

## Current Status
```
[RALPH STATUS] Task 9/12: Foundry reproducible deployment | NEXT | 57 tests passing
```
