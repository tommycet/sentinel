"""AgentLineage — artifact.touched span processor and lineage graph.

Tracks which AI agents touched which downstream artifacts (files, DB rows,
notes, vault paths) and builds a queryable lineage graph correlating agent
traces to real-world effects. Stdlib only (sqlite + collections).

The lineage graph is the v2 differentiator:  when a downstream write
happens (file write, db row, note edit), emit a span carrying
artifact.path, artifact.kind, trace_id, parent_span_id.  SigNoz's
unified store makes this possible — LLM-only competitors cannot join
agent spans to DB writes or vault edits.

Usage:
    graph = ArtifactLineageGraph()
    graph.record("agent-1", "file:/vault/notes/idea.md", trace_id="abc123")
    touched = graph.effects_of("agent-1")
    report  = graph.export_markdown()
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artifact_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id    TEXT NOT NULL,
    artifact    TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,    -- file | db | note | vault | api
    trace_id    TEXT DEFAULT '',
    span_id     TEXT DEFAULT '',
    parent_span_id TEXT DEFAULT '',
    action      TEXT DEFAULT 'touched',   -- touched | written | edited | deleted
    cost_usd    REAL DEFAULT 0.0,
    metadata_json TEXT DEFAULT '{}',
    ts          REAL NOT NULL,
    created_at  TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_artifact_agent ON artifact_events(agent_id);
CREATE INDEX IF NOT EXISTS idx_artifact_art   ON artifact_events(artifact);
CREATE INDEX IF NOT EXISTS idx_artifact_trace ON artifact_events(trace_id);
CREATE INDEX IF NOT EXISTS idx_artifact_ts    ON artifact_events(ts);
"""


def _infer_kind(artifact: str) -> str:
    """Infer artifact kind from the path/uri.  Stdlib only."""
    if artifact.startswith(("http://", "https://")):
        return "api"
    if artifact.startswith(("postgres://", "mysql://", "sqlite:", "db:")):
        return "db"
    if "/.obsidian/" in artifact or artifact.startswith("vault:"):
        return "vault"
    if artifact.endswith((".md", ".txt", ".json", ".yaml", ".yml", ".py")):
        return "file"
    return "file"


@dataclass(frozen=True, slots=True)
class TouchEvent:
    """One agent→artifact touch, hydrated from the store."""
    id: int
    agent_id: str
    artifact: str
    artifact_kind: str
    trace_id: str
    span_id: str
    parent_span_id: str
    action: str
    cost_usd: float
    metadata: dict[str, Any]
    ts: float


class ArtifactLineageGraph:
    """Thread-safe lineage graph backed by SQLite.

    Nodes:  agent_id, artifact, trace_id  (three node types).
    Edges:  agent→artifact (touched),  agent→trace (emitted),  trace→artifact (caused).
    """

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or os.environ.get(
            "SENTINEL_LINEAGE_DB", ":memory:"
        )
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()
        except BaseException:
            self._conn.close()
            raise

    def record(
        self,
        agent_id: str,
        artifact: str,
        *,
        trace_id: str = "",
        span_id: str = "",
        parent_span_id: str = "",
        action: str = "touched",
        cost_usd: float = 0.0,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Record one agent→artifact touch. Returns the row id."""
        if self._conn is None:
            raise RuntimeError("graph is closed")
        kind = _infer_kind(artifact)
        meta = json.dumps(metadata or {}, sort_keys=True)
        ts = time.time()
        with self._lock:
            cur = self._conn.execute(
                """INSERT INTO artifact_events
                   (agent_id, artifact, artifact_kind, trace_id, span_id,
                    parent_span_id, action, cost_usd, metadata_json, ts)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (agent_id, artifact, kind, trace_id, span_id,
                 parent_span_id, action, cost_usd, meta, ts),
            )
            self._conn.commit()
            rid = cur.lastrowid
        return int(rid) if rid is not None else 0

    def effects_of(self, agent_id: str, *, since: float = 0.0) -> list[TouchEvent]:
        """Return all artifacts touched by an agent (newest first)."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, agent_id, artifact, artifact_kind, trace_id,
                          span_id, parent_span_id, action, cost_usd,
                          metadata_json, ts
                   FROM artifact_events
                   WHERE agent_id=? AND ts >= ?
                   ORDER BY ts DESC""",
                (agent_id, since),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def causes_of(self, artifact: str, *, since: float = 0.0) -> list[TouchEvent]:
        """Return all agents that touched a given artifact (newest first)."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, agent_id, artifact, artifact_kind, trace_id,
                          span_id, parent_span_id, action, cost_usd,
                          metadata_json, ts
                   FROM artifact_events
                   WHERE artifact=? AND ts >= ?
                   ORDER BY ts DESC""",
                (artifact, since),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def trace_lineage(self, trace_id: str) -> list[TouchEvent]:
        """Return all artifact touches sharing this trace_id."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, agent_id, artifact, artifact_kind, trace_id,
                          span_id, parent_span_id, action, cost_usd,
                          metadata_json, ts
                   FROM artifact_events
                   WHERE trace_id=?
                   ORDER BY ts""",
                (trace_id,),
            ).fetchall()
        return [_row_to_event(r) for r in rows]

    def export_markdown(self, *, since: float = 0.0) -> str:
        """Export the lineage graph as a Markdown report.

        This is the "Export lineage map as Markdown report" winning-feature
        artifact — drops a file the vault itself can read (meta: the agent
        that observes lineage also writes lineage reports).
        """
        with self._lock:
            rows = self._conn.execute(
                """SELECT id, agent_id, artifact, artifact_kind, trace_id,
                          span_id, parent_span_id, action, cost_usd,
                          metadata_json, ts
                   FROM artifact_events WHERE ts >= ?
                   ORDER BY ts""",
                (since,),
            ).fetchall()
        events = [_row_to_event(r) for r in rows]

        # Group by agent
        by_agent: dict[str, list[TouchEvent]] = defaultdict(list)
        for e in events:
            by_agent[e.agent_id].append(e)

        lines = [
            "# Agent Lineage Report",
            "",
            f"Generated: {datetime.now(timezone.utc).isoformat()}",
            f"Events: {len(events)}",
            "",
        ]
        for agent, touches in sorted(by_agent.items()):
            lines.append(f"## Agent: `{agent}`")
            lines.append("")
            total_cost = sum(t.cost_usd for t in touches)
            if total_cost:
                lines.append(f"Total cost: **${total_cost:.4f}**")
                lines.append("")
            lines.append("| Artifact | Kind | Action | Trace | Cost | Time |")
            lines.append("|----------|------|--------|-------|------|------|")
            for t in touches:
                ts_str = datetime.fromtimestamp(
                    t.ts, timezone.utc
                ).strftime("%Y-%m-%d %H:%M:%S")
                lines.append(
                    f"| `{t.artifact}` | {t.artifact_kind} | {t.action} "
                    f"| `{t.trace_id[:8] or '-'}` | ${t.cost_usd:.4f} | {ts_str} |"
                )
            lines.append("")
        if not events:
            lines.append("_(no lineage events recorded)_")
        return "\n".join(lines)

    def export_dot(self, *, since: float = 0.0) -> str:
        """Export_graphviz-style DOT digraph for visualization."""
        with self._lock:
            rows = self._conn.execute(
                """SELECT agent_id, artifact, artifact_kind, action, trace_id
                   FROM artifact_events WHERE ts >= ?""",
                (since,),
            ).fetchall()
        lines = ["digraph lineage {", '  rankdir="LR";', '  node [shape=box];']
        agents: set[str] = set()
        artifacts: set[str] = set()
        for agent, art, kind, action, trace in rows:
            agents.add(agent)
            artifacts.add(art)
            lines.append(
                f'  "{agent}" -> "{art}" '
                f'[label="{action}", color=blue];'
            )
        for a in sorted(agents):
            lines.append(f'  "{a}" [shape=ellipse, color=green];')
        for a in sorted(artifacts):
            lines.append(f'  "{a}" [shape=box, color=orange];')
        lines.append("}")
        return "\n".join(lines)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None  # ponytail: guard double-close; ceiling = 1 caller, add refcount if multi-owner


def _row_to_event(row: tuple) -> TouchEvent:
    return TouchEvent(
        id=row[0],
        agent_id=row[1],
        artifact=row[2],
        artifact_kind=row[3],
        trace_id=row[4],
        span_id=row[5],
        parent_span_id=row[6],
        action=row[7],
        cost_usd=row[8],
        metadata=json.loads(row[9]) if row[9] else {},
        ts=row[10],
    )


# -- Span processor (no opentelemetry dependency — emits OTLP/HTTP JSON) -----

def emit_artifact_touched_span(
    agent_id: str,
    artifact: str,
    *,
    trace_id: str = "",
    span_id: str = "",
    parent_span_id: str = "",
    action: str = "touched",
    cost_usd: float = 0.0,
) -> bool:
    """Emit an ``artifact.touched`` OTLP/HTTP span to the configured SigNoz endpoint.

    This is the synthetic span event from the v2 build plan:  "when a
    downstream write happens (file write, db row, note edit), emit a span
    carrying ``artifact.path``, ``artifact.kind``, ``trace_id``,
    ``parent_span_id``."

    Inline here (not via telemetry.export_span) so the lineage processor
    stays self-contained and independently testable.
    """
    # Lazy import to avoid circular at module load
    from .telemetry import export_span

    kind = _infer_kind(artifact)
    return export_span(
        "artifact.touched",
        {
            "agent.id": agent_id,
            "artifact.path": artifact,
            "artifact.kind": kind,
            "artifact.action": action,
            "trace.id": trace_id,
            "span.id": span_id,
            "parent.span.id": parent_span_id,
            "cost.usd": cost_usd,
        },
        start_time=time.time(),
    )
