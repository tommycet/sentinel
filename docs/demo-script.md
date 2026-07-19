# Sentinel — 60-Second Demo Script

## Setup (0-15s)
```bash
foundryctl cast -f casting.yaml
# SigNoz + Sentinel deployed
```

## Normal Agent (15-25s)
```bash
PYTHONPATH=src:. python3 demo/runaway_agent.py --threshold 8
# 5 normal calls — no quarantine
```

## Runaway Loop (25-45s)
```bash
# 15 identical failing calls
# At repetition 8: quarantine triggers
grep QUARANTINE output.txt  # -> "QUARANTINE: tool=failing_tool repetition=8"
```

## Dashboard (45-55s)
Visit SigNoz at localhost:8080 — see quarantine count, latency, agent activity.

## Cleanup (55-60s)
```bash
curl -X POST http://localhost:8090/incidents/<id>/release  # restore access
```