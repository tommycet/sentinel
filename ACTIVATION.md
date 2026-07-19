# ACTIVATION.md — Launching Ralph for Sentinel

## Prerequisites

- Docker + Docker Compose installed
- `foundryctl` installed (`curl -fsSL https://signoz.io/foundry.sh | bash`)
- Python 3.11+ (with `pip`)
- `claude` CLI logged in (for Ralph)
- `ralph` CLI installed at `/root/.local/bin/ralph`
- Hermes Agent running (default profile)

## Quick Start

### 1. Review the Spec

Review the `.ralph/` directory:
```bash
cd /root/signoz-sentinel
cat .ralph/PROMPT.md       # The Ralph contract (read this first)
cat .ralph/fix_plan.md     # The task checklist
ls .ralph/specs/           # Component specifications
```

### 2. Launch Ralph

```bash
cd /root/signoz-sentinel && ralph --monitor
```

Ralph will:
1. Start a tmux session
2. Run `claude --dangerously-skip-permissions` inside it
3. Execute tasks from `fix_plan.md` in order
4. Report status after each loop iteration

### 3. Monitor Progress

Watch the tmux session:
```bash
tmux capture-pane -t ralph -p -S -30
```

Or check Ralph's monitor:
```bash
ralph-monitor
```

### 4. Useful Flags

| Flag | Purpose |
|------|---------|
| `--verbose` | More detailed output |
| `--live` | Real-time stream of Claude's output |
| `--timeout 30` | Min/loop timeout (default) |
| `--calls 50` | Cap API calls/hr |
| `--backup` | Git backup per loop |

### 5. Stopping & Recovery

**Graceful stop:** Press `Ctrl+C` in the Ralph terminal.

**Emergency stop:** `tmux kill-session -t ralph`

**Recovery after crash:**
```bash
git checkout .   # Revert unwanted changes
ralph --reset-session   # Reset Ralph's internal state
```

**Circuit breaker (if Ralph keeps failing):**
```bash
ralph --reset-circuit
```

### 6. Manual Override

If you need to run Claude Code directly:
```bash
cd /root/signoz-sentinel
claude -p "Implement Task 3: HMAC webhook auth + replay protection" --allowedTools "Read,Edit,Write,Bash" --max-turns 15
```

Or inside tmux for interactive work:
```bash
tmux new-session -d -s sentinel-dev -x 140 -y 40
tmux send-keys -t sentinel-dev 'cd /root/signoz-sentinel && claude' Enter
sleep 5 && tmux send-keys -t sentinel-dev Enter  # Trust dialog
tmux send-keys -t sentinel-dev 'Implement Task 3...' Enter
```

## Verification Commands

After Ralph completes all tasks:

```bash
# Unit tests
python -m unittest discover -s tests -v

# Deploy check
foundryctl gauge -f casting.yaml

# E2E
bash scripts/e2e.sh
```

## Tear Down

```bash
# Stop Sentinel (if running directly)
pkill -f "sentinel --port"

# Stop Foundry deployment
docker compose -f pours/deployment/compose.yaml down

# Clean up
rm -rf pours/ sentinel-data/ sentinel.db
```

## Troubleshooting

**Problem:** Ralph says "Claude Code not found"
**Fix:** `export PATH=$PATH:/root/.local/bin && ralph --monitor`

**Problem:** Foundry errors on `cast`
**Fix:** `foundryctl gauge -f casting.yaml --debug` to see what's missing

**Problem:** Sentinel refuses webhook with "401 Unauthorized"
**Fix:** Check `SENTINEL_WEBHOOK_SECRET` matches on both sides

**Problem:** Tests fail
**Fix:** Run the failing test with `-v` to see the full traceback, fix, re-run.

## The Canonical Driver

The Ralph loop is at `/root/.ralph/ralph_loop.sh`. This is the only supported way to run Ralph.
