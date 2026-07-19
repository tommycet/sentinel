# Sentinel Testing Guide

## Prerequisites
```
source .venv/bin/activate 2>/dev/null || python3 -m venv .venv && source .venv/bin/activate && pip install -e .
```

## Automated Tests
```
PYTHONPATH=src:. python3 -m unittest discover -s tests -v
```

## 10 Manual Verification Checks

### 1. Fresh Foundry cast succeeds
```
foundryctl gauge -f casting.yaml
foundryctl cast -f casting.yaml
docker ps | grep signoz-ingester
```

### 2. Normal agent not quarantined
```
PYTHONPATH=src:. python3 -c "
from sentinel.model import parse_alert
a = parse_alert({'status':'firing','alertname':'T','labels':{'agent_id':'n','credential_id':'c'},'startsAt':'2026-07-19T00:00:00Z'})
assert not a.needs_quarantine
print('PASS')
"
```

### 3. Runaway triggers quarantine once
```
PYTHONPATH=src:. python3 demo/runaway_agent.py --threshold 8 2>&1 | grep -c QUARANTINE
# Expected: 1
```

### 4. Duplicate webhook = no second action
```
curl -X POST http://localhost:8090/alerts -H 'Content-Type: application/json' -d '...' | grep -c duplicate
```

### 5. Forged/stale webhooks return 401
```
curl -o /dev/null -w '%{http_code}' -X POST http://localhost:8090/alerts -H 'X-Sentinel-Timestamp: 1' -H 'X-Sentinel-Signature: 0' -d '{}'
# Expected: 401
```

### 6-10. See scripts/e2e.sh for full automated run
```
bash scripts/e2e.sh
```