"""AgentLineage demo — "I can see what my agent *caused*."

Simulates a Hermes-style agent running a brain-capture cron that:
  1. Calls 9router (LLM gateway) — $0.0021 per call
  2. Writes 3 notes to an Obsidian-style vault
  3. Edits a DB row
  4. Calls an external API

Then shows:
  - The lineage graph (agent → artifact → trace correlation)
  - The cost breakdown per artifact
  - The exportable Markdown report

This is the v2 winning-feature demo:  SigNoz's unified store makes the
lineage map possible — LLM-only competitors cannot join agent spans to
DB writes or vault edits.

Usage:
    PYTHONPATH=src:. python3 demo/agent_lineage.py
    PYTHONPATH=src:. python3 demo/agent_lineage.py --json   # machine-readable
    PYTHONPATH=src:. python3 demo/agent_lineage.py --dot    # Graphviz DOT
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

from sentinel.lineage import ArtifactLineageGraph, emit_artifact_touched_span


def _shr(s: str) -> str:
    """Short hash of a string, used as fake trace id for the demo."""
    import hashlib
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def run_lineage_demo(graph: ArtifactLineageGraph | None = None) -> ArtifactLineageGraph:
    """Run the lineage demo scenario. Returns the populated graph."""
    g = graph or ArtifactLineageGraph(":memory:")

    # Scenario:  Hermes cron "brain-capture" touches 5 artifacts in one run.
    trace_id = _shr("lineage-run-001")

    # 1. Agent calls 9router (LLM gateway) — cost recorded
    g.record(
        agent_id="agent-lineage-test",
        artifact="9router:gpt-4o-mini",
        trace_id=trace_id,
        span_id=_shr("span-9router"),
        action="called",
        cost_usd=0.0021,
        metadata={"model": "gpt-4o-mini", "tokens": 1200},
    )

    # 2. Agent writes 3 vault notes from the LLM output
    for i, note in enumerate(["ideas.md", "tasks.md", "contacts.md"]):
        g.record(
            agent_id="agent-lineage-test",
            artifact=f"vault://obsidian/{note}",
            trace_id=trace_id,
            span_id=_shr(f"span-note-{i}"),
            parent_span_id=_shr("span-9router"),
            action="written",
            metadata={"lines": 42 + i * 7},
        )

    # 3. Agent edits a DB row (contacts table)
    g.record(
        agent_id="agent-lineage-test",
        artifact="db:contacts.user_id=42",
        trace_id=trace_id,
        span_id=_shr("span-db-update"),
        parent_span_id=_shr("span-9router"),
        action="edited",
        metadata={"table": "contacts", "row": 42},
    )

    # 4. Agent calls an external API (enrichment)
    g.record(
        agent_id="agent-lineage-test",
        artifact="https://api.enrichment.dev/v1/lookup",
        trace_id=trace_id,
        span_id=_shr("span-api"),
        parent_span_id=_shr("span-9router"),
        action="called",
        cost_usd=0.0008,
        metadata={"status": 200},
    )

    # Second agent touches one of the same notes — shows cross-agent lineage
    g.record(
        agent_id="agent-monitor-v1",
        artifact="vault://obsidian/tasks.md",
        trace_id=_shr("daily-briefing-run-001"),
        span_id=_shr("span-briefing-1"),
        action="read",
        metadata={"reason": "daily tasks pull"},
    )

    return g


def main() -> None:
    parser = argparse.ArgumentParser(
        description="AgentLineage demo — agent→artifact lineage graph"
    )
    parser.add_argument("--json", action="store_true",
                        help="Output machine-readable JSON")
    parser.add_argument("--dot", action="store_true",
                        help="Output Graphviz DOT digraph")
    parser.add_argument("--markdown", action="store_true",
                        help="Output Markdown lineage report")
    parser.add_argument("--db-path", default=":memory:",
                        help="SQLite path (default: in-memory)")
    args = parser.parse_args()

    graph = ArtifactLineageGraph(args.db_path)

    # Emit artifact.touched spans to SigNoz (best-effort, no crash if offline)
    # We emit 1 span per touch to demonstrate the OTLP export path.
    try:
        emit_artifact_touched_span(
            "agent-lineage-test",
            "vault://obsidian/ideas.md",
            trace_id=_shr("lineage-run-001"),
            action="written",
        )
    except Exception:
        pass  # Best-effort — SigNoz may not be running during the demo

    g = run_lineage_demo(graph)

    if args.json:
        events = g.effects_of("agent-lineage-test")
        out = [
            {
                "agent_id": e.agent_id,
                "artifact": e.artifact,
                "kind": e.artifact_kind,
                "action": e.action,
                "trace_id": e.trace_id,
                "cost_usd": e.cost_usd,
            }
            for e in events
        ]
        print(json.dumps(out, indent=2))
    elif args.dot:
        print(g.export_dot())
    elif args.markdown:
        print(g.export_markdown())
    else:
        # Human-readable default
        print("\n╔══════════════════════════════════════════════════════════════╗")
        print("║         AgentLineage — what my agent *caused*               ║")
        print("╚══════════════════════════════════════════════════════════════╝\n")

        print("Agent: agent-lineage-test  (trace: lineage-run-001)\n")
        events = g.effects_of("agent-lineage-test")
        total_cost = sum(e.cost_usd for e in events)
        print(f"  Total artifacts touched: {len(events)}")
        print(f"  Total cost:             ${total_cost:.4f}")
        print()
        print("  Lineage graph:")
        print("  ┌─────────────────────┐    ┌────────────────────┐    ┌───────────────────┐")
        print("  │ agent-lineage-test│───▷│ 9router:gpt-4o-mini│───▷│ vault://obsidian/ │")
        print("  │  (agent)            │    │  ($0.0021)         │    │  ideas.md          │")
        print("  └──────────┬──────────┘    └────────────────────┘    │  tasks.md          │")
        print("             │                                         │  contacts.md       │")
        print("             ├───▷ db:contacts.user_id=42 (edited)     └───────────────────┘")
        print("             └───▷ https://api.enrichment.dev/ (called, $0.0008)\n")

        for e in events:
            cost_str = f"${e.cost_usd:.4f}" if e.cost_usd else "—"
            print(f"  • {e.artifact:45s}  {e.action:8s}  cost={cost_str}  trace={e.trace_id[:8]}")

        print()
        print("  Cross-agent lineage (who else touched tasks.md?):")
        causes = g.causes_of("vault://obsidian/tasks.md")
        for c in causes:
            print(f"    ← {c.agent_id}  ({c.action})  trace={c.trace_id[:8]}")

        print()
        print("  Markdown report (first 20 lines):")
        print("  " + "\n  ".join(g.export_markdown().splitlines()[:20]))
        print("\n  [demo] AgentLineage feature works.  Use --json, --dot, or --markdown for exports.")

    g.close()


if __name__ == "__main__":
    main()
