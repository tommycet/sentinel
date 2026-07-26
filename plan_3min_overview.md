Plan — 3-Minute Final Video (Overview + AgentLineage + Live Program)
Target: 3 minutes (≤180s) — can extend to 180s max.

=== STRUCTURE ===

PART 1 — OVERVIEW (0-35s): Landing page scroll
- 0-5s: Hero with circuit diagram visible + title
- 5-12s: Metrics strip (stats visible)
- 12-20s: Architecture section (mono flow line visible)
- 20-28s: Lineage artifacts cards (AgentLineage Graph, Architecture Flow, Security Audit, Real-Time Stats)
- 28-35s: Security audit section (14 verified fixes listed)

PART 2 — AGENT LINEAGE DASHBOARD (35-75s): Real code output
- 35-40s: Launch agent_lineage.py (typing command)
- 40-55s: Full output visible — 6 artifacts, cost $0.0029, DOT graph, vault/DB/API artifacts
- 55-65s: Cross-agent lineage section visible — inventory-agent-3 contamination shown
- 65-75s: Cost breakdown and artifact table

PART 3 — LIVE PROGRAM DEMONSTRATION (75-165s): Actual server responding
- 75-85s: Start server (python -m sentinel) — real output visible
- 85-95s: Health check (/livez) — real 200 OK response visible
- 95-115s: Send signed alert (send_signed_alert.py or curl with HMAC) — real POST, real quarantine response
- 115-135s: Lineage query (/lineage) — real JSON response with artifacts array
- 135-155s: Security audit (tests running — 102 passed visible in terminal)
- 155-165s: Release (/release) — audit trail shown
- 165-180s: Global confirmation — works with any provider/system

=== VERIFICATION CHECKLIST ===
□ Video file exists at demo/videos/final_3min_overview.mp4 (≤180s)
□ Tunnel serves it: curl -w "%{http_code}" <url>/final_3min_overview.mp4 = 200
□ Video contains landing page section (circuit visible, no black box)
□ Video contains agent_lineage.py output (agent names are global, no hermes)
□ Video contains actual terminal commands with server responses
□ Narration matches: mentions AgentLineage differentiator, cross-agent contamination, 15 fixes, 102 tests, global provider
□ Frontend anti-slop verified: no shadcn tokens, correct fonts/colors
□ GitHub commit pushed

=== FILE REFERENCES ===
Landing page: frontend/index.html (embedded SVG circuit, anti-slop)
AgentLineage demo: demo/agent_lineage.py (global agent names, real output)
Video output: demo/videos/final_3min_overview.mp4
Audio: demo/audio/narration_3min.mp3
Tunnel URL: https://calls-advertisers-valentine-dont.trycloudflare.com/
Plan file: /root/signoz-sentinel/plan_3min_overview.md (this file)
GitHub: https://github.com/tommycet/sentinel (master branch, commit will be pushed)
