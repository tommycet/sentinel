# Video Production Plan — Actual Program in Action

This plan produces a video showing the REAL Sentinel server responding to REAL requests.
Each narration line is mapped to a terminal event that must be visible in the video.

## Setup (before recording)
1. Start server: PYTHONPATH=src:. python -m sentinel --port 8095 --db-path /tmp/prod_demo.db --dry-run --webhook-secret demo-secret
2. Verify health: curl -s http://localhost:8095/health

## Video sequence (139.3s sync — each section ≈ narration duration)

### Section 1 (0-15s): Server + Health
- Terminal: Type 'python -m sentinel ...' (typing animation)
- Show server start output: "Sentinel listening on 127.0.0.1:8095"
- Execute: curl -s http://localhost:8095/health | python -m json.tool
- Visible result: {"status":"ok","version":"0.1.0"}

### Section 2 (15-38s): Alert Pipeline
- Execute: python3 send_alert_demo.py (simulated HMAC-signed alert)
- Show terminal output: HMAC computed, POST sent, 200 OK
- Show response: {"status":"quarantined","incident_id":"...","agent_id":"..."}

### Section 3 (38-60s): Lineage Query
- Execute: curl -s 'http://localhost:8095/lineage?agent=checkout-agent-7'
- Show full JSON response with artifacts array and cross-agent contamination
- Highlight: "inventory-agent-3" found as contamination source

### Section 4 (60-80s): Security
- Show audit grid (12 fixes verified) as terminal output
- Execute: python3 -m unittest discover tests/
- Show: 102 passed

### Section 5 (80-105s): Release
- Execute: curl -X POST 'http://localhost:8095/incidents/{id}/release'
- Show response: {"status":"released","audit_trail":[...]}

### Section 6 (105-131s): Global + Close
- Show terminal: echo "Works with 9router, Groq, OpenRouter globally"
- Final summary lines

## Verification steps per user instruction
✓ Verify URL serves video (tunnel check)
✓ Verify narration audio plays (ffprobe duration match)
✓ Verify no black box (vision screenshot of hero + cards)
✓ Verify 102 tests pass
✓ Verify video shows REAL program (not only narration over static images)
