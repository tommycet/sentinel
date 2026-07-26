# AgentLineage — "I can see what my agent *caused*."

> The v2 winning-feature differentiator for Sentinel.

## The Problem

You can see what your AI agent **did** — the LLM calls, the tool invocations, the token counts. You cannot see what your agent **caused** — which files it wrote, which DB rows it edited, which vault notes it created, which APIs it called.

Today the answer requires grepping across 4 systems. SigNoz has the data — it just doesn't connect it into a lineage view.

## The Differentiator

**Only SigNoz makes this possible.** LLM-siloed competitors (Langfuse, Phoenix, Breadcrumb, OpenLIT, AgentWatch) store only LLM spans. They cannot join agent traces to DB writes, file writes, or vault edits because they lack the unified ClickHouse store.

SigNoz has:
- **Traces** — the agent's LLM and tool-call spans
- **Metrics** — per-call token cost, request latency
- **Logs** — the actual file writes, DB queries, and API calls
- **ClickHouse** — all in one store, joinable on `trace_id`

AgentLineage closes the loop: agent → artifact → trace correlation, queryable, exportable.

## Architecture

```
  Agent (Hermes)              SigNoz (ClickHouse)           AgentLineage
┌──────────────────┐      ┌──────────────────────┐      ┌─────────────────────┐
│ gen_ai.* spans   │─────▷│ signoz_spans         │◁─────│ artifact.touched    │
│ tool_call spans  │ OTLP │ signoz_metrics       │ SQL  │ lineage graph       │
│ artifact.touched │─────▷│ signoz_logs          │      │ SQLite + export     │
└──────────────────┘      └──────────────────────┘      └─────────────────────┘
                                    │
                                    ▼
                          ┌──────────────────┐
                          │ Dashboard (JSON) │
                          │ Lineage graph    │
                          │ Cost per artifact│
                          │ Cross-agent view │
                          └──────────────────┘
```

## Usage

```bash
# Record lineage events
PYTHONPATH=src python3 demo/agent_lineage.py

# Export as JSON (machine-readable)
PYTHONPATH=src python3 demo/agent_lineage.py --json

# Export as Graphviz DOT
PYTHONPATH=src python3 demo/agent_lineage.py --dot

# Export as Markdown report (drops into the vault itself)
PYTHONPATH=src python3 demo/agent_lineage.py --markdown
```

## Programmatic API

```python
from sentinel.lineage import ArtifactLineageGraph

graph = ArtifactLineageGraph("/tmp/lineage.db")

# Record an agent touching an artifact
graph.record(
    agent_id="hermes-brain-capture",
    artifact="vault://obsidian/ideas.md",
    trace_id="abc123",
    action="written",
    cost_usd=0.0021,
    metadata={"lines": 42},
)

# Query: what did this agent touch?
effects = graph.effects_of("hermes-brain-capture")

# Query: who touched this artifact? (cross-agent lineage)
causes = graph.causes_of("vault://obsidian/ideas.md")

# Query: lineage of a trace
trace_events = graph.trace_lineage("abc123")

# Export
report = graph.export_markdown()  # → vault-ready report
dot    = graph.export_dot()       # → graphviz
```

## SigNoz surfaces deeply used

1. **OTLP/OTel ingest** — `artifact.touched` synthetic spans emitted via `emit_artifact_touched_span()`
2. **Traces Query Builder + raw ClickHouse SQL** — lineage joins across `signoz_spans`
3. **Metrics** — per-artifact token cost from `gen_ai.usage.cost` gauge
4. **Logs** — file writes correlated to the trace via shared `trace_id`
5. **Dashboards** — `deploy/dashboard.json` includes lineage panels
6. **Trace-based alerts** — agent touched a protected vault path → webhook
7. **MCP server** — any LLM agent can query its own lineage (read-only)

## Safety

- Reversible only — lineage records are append-only audit entries
- No secrets in spans — `credential.id` is SHA-256 hashed in `telemetry.py`
- Thread-safe SQLite (WAL mode)
- Best-effort OTLP export — never crashes Sentinel if SigNoz is offline

## Why this wins

| Criterion | AgentLineage |
|-----------|-------------|
| Potential Impact | Every infra operator running AI agents that touch the world feels this daily. |
| Creativity | New category: "agent→infra lineage graph from an observability platform." Judges won't see 30 of these. |
| Technical Excellence | Real OTel processor, real ClickHouse joins, real demoable end-to-end lineage. |
| Best Use of SigNoz | Load-bearing. Uses EVERYTHING: OTel, Query Builder, raw ClickHouse, metrics, logs, dashboards, alerts, MCP. |
| User Experience | Polished CLI demo; one-click export to vault; no credit card needed. |
| Presentation | "I can see what my agent did. I can't see what it *caused*." — the line judges quote back. |
