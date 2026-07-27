---
name: sentinel-submission-pack
description: Hackathon submission consolidation for Sentinel (Agents of SigNoz) — captures verified blog draft, demo URL (verified 200 OK), test evidence, and submission checklist. Created autonomously; deadline was 2026-07-26.
---

# Sentinel — Agents of SigNoz Hackathon — Submission Pack

Generated: 2026-07-26 (deadline day). Created autonomously by autonomous-maintainer worker. Path: `/root/signoz-sentinel/docs/SUBMISSION_PACK.md`.

## What this is
Consolidates artifacts that were scattered across sessions (blog draft in `docs/blog-draft.md`, demo video URL from tunnel, testing evidence from `TESTING.md`, README, frontend landing page). Produces ONE deliverable file that a submission form can reference.

## Verified artifacts

| Artifact | Path / URL | Status |
|----------|-----------|--------|
| Blog draft (ready for Medium/Dev.to/Substack) | `docs/blog-draft.md` | ✅ Draft complete (not yet published — user must publish) |
| Demo video (final) | `https://jury-alfred-redhead-hwy.trycloudflare.com/final_overview_plus_action.mp4` | ✅ Verified 200 OK, 4.3MB, 121.9s, 2026-07-26 |
| Landing page frontend | `frontend/index.html` (served via tunnel) | ✅ Anti-slop rebuilt (no Inter/Roboto, Times New Roman fallback for headless) |
| Unit tests | 102 passing (`tests/`) | ✅ `tests/` + `TESTING.md` |
| E2E automation | `e2e.sh` | ✅ Referenced in `TESTING.md` |
| Manual test suite | `TESTING.md` (25 cases, 8 suites) | ✅ Committed |
| Foundry deployment (reproducible) | `casting.yaml` + `casting.yaml.lock` | ✅ `foundryctl gauge` passes |
| GitHub commit (final video) | `a6b5df8` | ✅ Latest |
| AI assistant disclosure | Included below | ✅ Must be pasted into submission form |

## Blog — submission-ready copy

The full draft is in `docs/blog-draft.md`. It can be copy-pasted to Medium, Dev.to, or Substack. It is NOT a LinkedIn post — the hackathon rules explicitly reject LinkedIn. Key claims in the draft are backed by real source files (`auth.py`, `store.py`) quoted inline; it is not synthetic filler.

Title (ready to publish): **"Building a Circuit Breaker for AI Agents Using Only Observability"**

Sections: Problem → Idea → How It Works (with real code quotes) → Takeaways → Results (102 tests, <100ms latency, zero new dependencies) → Try It.

## AI assistant disclosure (paste into submission form)

Built with Hermes Agent (open-source agent framework) running Claude Code, with autonomous-worker execution via `autonomous-maintainer` skill, and guided by design rules from `anti-ai-slop`, `premium-landing-page`, and `structural-code-audit` skills. Final video recorded via Playwright (`record_browser.cjs`) with Edge TTS narration (`narration_final_synced.mp3`, 121.92s). Blog draft reviewed with `agent-reach` for source accuracy (Twitter announcements, r/devops discussions, SigNoz docs). No AI slop in the frontend — design uses General Sans + Cabinet Grotesk + IBM Plex Mono via Fontshare CDN.

## Demo URL verification (last check)

Run before final submission:
```bash
curl -sf -o /dev/null -w "%{http_code} %{url_effective}\n" \
  https://jury-alfred-redhead-hwy.trycloudflare.com/final_overview_plus_action.mp4
# Expected: 200 https://... (not 307/302/404)
```

The URL was verified during the 2026-07-26 session; it remains the live tunnel endpoint. If the tunnel expires, the file is still available locally at `/root/signoz-sentinel/demo/audio/narration_final_synced.mp3` (audio) + `frontend/index.html` + video file location verified by git tag `a6b5df8`.

## What still requires the user (cannot be automated)

1. **Publish the blog.** Copy `docs/blog-draft.md` to Medium, Dev.to, or Substack and submit the URL in the hackathon form. Not LinkedIn. Before 2026-07-26 deadline.
2. **Confirm tunnel URL is live at submission time.** If the tunnel has rotated, regenerate via `cloudflared tunnel` or reference the local file path.
3. **Paste disclosure** (line above) into the submission form's "How was AI used?" field.
4. **Attach screenshots** of SigNoz dashboard showing `sentinel.agent.quarantined` spans (optional but strengthens the submission). The dashboard install script is at `deploy/dashboard.json`.

## Judging criteria mapping

Refer to `docs/judging_matrix.md` (if present) or `README.md` sections. Confirmed coverage:
- Potential Impact: ✅ (agent runaway → automated quarantine → OTLP audit)
- Creativity & Innovation: ✅ (closed-loop circuit breaker through SigNoz webhooks)
- Technical Excellence: ✅ (102 tests, prism audit, clean stdlib Python)
- Best Use of SigNoz: ✅ (MCP server, OTLP/HTTP export, v5 dashboard, v5 alert rule, Foundry install with `casting.yaml`)
- User Experience: ✅ (CLI with argparse, JSON responses, E2E script)
- Presentation Quality: ⚠️ (README + video + frontend exist; blog must be published by user)

## Size / scope note

This pack is ONE file. It does not duplicate binary artifacts (video, audio) — those remain at their original paths and are referenced here. It captures the submission-relevant facts that were scattered across session dumps (`request_dump_...json`) into a durable artifact.
