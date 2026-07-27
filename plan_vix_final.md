PLAN — V3 VIDEO FIX (SCREEN DULL @1:20 + AGENTLINEAGE SCROLL)

== ROOT CAUSE ==
1. **Screen dull at 75s (~1:20)**: `page.setContent()` is used mid-recording to switch from Part 2 to Part 3. This wipes the DOM and starts a new HTML page load. The 5 concatenated calls before muxing the audio — frames 75s through 165s are 5,620 bytes each (small black frame) while the JS animation typewriter hasn't rendered yet. Solution: **don't use setContent**. Record ONE single-page experience where everything is sequential.

2. **AgentLineage dashboard not scrolled**: In the current video, the AgentLineage output uses a single-page viewport with `overflow:hidden`. The full lineage table (6 artifacts, DOT graph, cross-agent contamination) overflows but the page doesn't scroll. Solution: **allow vertical scrolling** and run `page.evaluate('scrollBy(0, X)')` at timed intervals so the camera pans down through the entire AgentLineage output.

FIX STRATEGY:
- Use ONE page. No setContent() transitions.
- The page has three sequential "scenes" with height = 3x viewport
- Scene 1 (0%) — landing page rendered as first section
- Scene 2 (33%) — AgentLineage terminal output (full text, scrollable)
- Scene 3 (66%) — Live server terminal output (full text, scrollable)
- Use `page.evaluate('window.scrollTo({top: viewport*N, behavior: smooth})')` to pan up
  at precise moments matching narration timing.

SEQUENCE:
0-35s:  Show landing page (iframe to localhost:8090 or render as URL)
36-40s: Smooth scroll/fade to AgentLineage Section
41-85s: Scroll AgentLineage (artifact table, graph, cross-agent) — shows EVERYTHING by scrolling
86-90s: Fade to Live Terminal
91-165s: Scroll terminal (server start, health, alert, lineage, security, release, global)

VERIFICATION:
□ All three scenes visible (no black screen transitions)
□ AgentLineage shows FULL content (not truncated to viewport)
□ File at frontend/final_3min_overview.mp4
□ curl -w "%{http_code}" <url> = 200
□ File size < 8MB
□ File under 3 minutes
□ Frame at 80s > 10KB (not black/dull)
□ Frame at 120s > 10KB (not black/dull)
□ No Hermes references in narration or output
□ Circuit SVG visible in hero
□ 102 tests pass
□ GitHub push confirmed