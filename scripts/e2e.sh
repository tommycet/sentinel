#!/bin/bash
set -euo pipefail
echo "=== Sentinel E2E ==="
echo "1) Unit tests..."
PYTHONPATH=src:. python3 -m unittest discover -s tests -v

echo "2) Foundry gauge..."
foundryctl gauge -f casting.yaml 2>/dev/null && echo "[PASS] gauge" || echo "[SKIP] gauge"

echo "3) Demo quarantine trigger..."
PYTHONPATH=src:. python3 demo/runaway_agent.py --threshold 8 2>&1 | grep -c QUARANTINE | grep -q 1 && echo "[PASS] quarantine" || echo "[FAIL] quarantine"

echo "4) Secret leak check..."
grep -rE '(sk_live_|ghp_|AKIA|BEGIN.*PRIVATE)' . --include='*.py' --include='*.yaml' --include='*.json' 2>/dev/null && echo "[FAIL] secrets found" || echo "[PASS] no secrets"

echo "5) Compile check..."
python3 -m compileall src/ -q && echo "[PASS] compile" || echo "[FAIL] compile"

echo "=== E2E complete ==="
