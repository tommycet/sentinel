PLAN: VIDEO WITH OVERVIEW (LANDING PAGE) + LIVE DEMO (REAL PROGRAM)

DELIVERABLE: One video with TWO parts — (A) Landing page overview, (B) Actual program running
VIDEO NAME: demo/videos/final_overview_plus_action.mp4
NARRATION: demo/audio/final_narration.mp3

PART A — OVERVIEW (0s to ~45s) — Shows landing page features
1. Hero: Circuit diagram visible (no black box). Voice: "Sentinel — global agent runaway detection."
2. Stats strip: Voice: "Real-time metrics — 247 alerts, 18 quarantines, 1,847 lineage events."
3. Architecture: Voice: "One signal path — webhook → HMAC → SQLite → revoker → OTLP."
4. Lineage artifacts: Voice: "Every agent artifact traced — vault, DB, API. Cross-agent contamination detected."
5. Security audit: Voice: "15 verified fixes — HMAC replay protection, body-size guard, constant-time comparison."
6. Docs: Voice: "Full integration guide — webhook format, AgentLineage API, revocation flow."

PART B — LIVE ACTION (45s to ~135s) — Real Sentinel server running
Server runs continuously at :8095. Each scene executes ACTUAL commands against REAL endpoint.

7. Server start (visible in terminal): Voice: "Server started. HMAC webhook receiver on 8095. Dry-run revoker enabled."
8. Health check (real curl): Voice: "Health check passes — status ok, version 0.1.0."
9. Signed alert (real python script sending HMAC): Voice: "Agent detected — 14 repetitive payment calls. Signature verified."
10. Quarantine (real endpoint response): Voice: "Quarantined. Credential vault-key-prod revoked. Incident inc-001 created."
11. Lineage query (real curl response): Voice: "3 artifacts traced — vault read, DB mutation, Stripe API. Cross-agent: inventory-agent-3."
12. Security audit grid (displayed): Voice: "Body-size bypass fixed. Replay signatures TTL enforced. 102 tests pass."
13. Release (real POST): Voice: "Released post-review. Full audit trail preserved. Credential restored."
14. Global confirmation: Voice: "Works globally — any agent framework, any LLM provider: 9router, Groq, OpenRouter."

VERIFICATION STEPS (before delivering):
□ Start server: PYTHONPATH=src:. python -m sentinel --port 8095 --dry-run
□ Verify health endpoint responds (200, status ok)
□ Verify tunnel URL serves final video: curl -w "%{http_code}" https://jury-alfred-redhead-hwy.trycloudflare.com/final_overview_plus_action.mp4
□ Verify video plays through both parts (not frozen, no black box)
□ Confirm narration audio duration ≈ video duration
□ Confirm 102 tests pass
□ Confirm no "Hermes" references in video text

FILE INVENTORY:
Frontend: /root/signoz-sentinel/frontend/index.html (embedded SVG circuit)
Video file: /root/signoz-sentinel/demo/videos/final_overview_plus_action.mp4
Audio: /root/signoz-sentinel/demo/audio/final_narration.mp3
Tunnel: https://jury-alfred-redhead-hwy.trycloudflare.com/
GitHub: https://github.com/tommycet/sentinel (master branch)
Tests: 102/102 passing
