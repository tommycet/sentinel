
VIDEO STRUCTURE — 3 minutes, no black screen, full AgentLineage dashboard scrolled

SECTION 1 (0-30s): Landing Page Overview — live recording with scroll
- Hero (circuit diagram embedded)
- Metrics (stats strip)
- Architecture (mono flow line)
- Lineage artifacts cards (AgentLineage Graph shown)
- Security audit (audit grid, 15 fixes)

SECTION 2 (30-90s): AgentLineage Dashboard — FULL scroll through output
- Full AgentLineage.py output shown (6 artifacts, cost $0.0029)
- Lineage graph with DOT representation
- Artifact table (all 6 rows)
- Trace timeline (7 events)
- Cost breakdown
- Cross-agent contamination (agent-monitor-v1 contamination visible)
- Every line of the 53-line output visible through scrolling

SECTION 3 (90-180s): Live Program + Shell Demo
- Server start (python -m sentinel)
- Health check (/livez → 200 OK)
- HMAC-signed alert (real curl/post to live server)
- Quarantine response (real server response)
- Lineage query (real /lineage endpoint response)
- Security test suite (102 passed, real pytest)
- Release after review (real /release endpoint)
- Global confirmation (any provider)

VERIFICATION CHECKLIST:
□ No setContent() used (no blank/dull frames at 1:20 or any time)
□ Frame at 30s > 10KB (landing visible)
□ Frame at 60s > 10KB (lineage visible)
□ Frame at 90s > 10KB (lineage scroll visible)
□ Frame at 120s > 10KB (live terminal visible)
□ Frame at 150s > 10KB (security/release visible)
□ No black/dark frames
□ Tunnel URL serves video (200 OK, size ≈ expected)
□ GitHub pushed
□ Project is global (no hermes references)
□ 102 tests passing
□ Anti-slop design maintained
□ AgentLineage dashboard fully scrolled (all 53 lines visible through scroll)
□ Video under 8MB for Discord
