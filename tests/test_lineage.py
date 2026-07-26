"""Self-check: AgentLineage module works end-to-end.

Tests the winning-feature code without external dependencies.
Per lazy-senior rule: ONE runnable check behind each non-trivial feature.
"""
import os
import tempfile
import unittest

from sentinel.lineage import (
    ArtifactLineageGraph,
    emit_artifact_touched_span,
    _infer_kind,
)


class TestLineageSelfCheck(unittest.TestCase):
    def test_infer_kind_classifies_paths(self):
        self.assertEqual(_infer_kind("/home/note.md"), "file")
        self.assertEqual(_infer_kind("db:contacts.id=1"), "db")
        self.assertEqual(_infer_kind("https://example.com/api"), "api")
        self.assertEqual(_infer_kind("vault://obsidian/x.md"), "vault")

    def test_record_and_query(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        g = ArtifactLineageGraph(path)
        try:
            rid = g.record(
                agent_id="agent-1",
                artifact="vault://test.md",
                trace_id="t1",
                action="written",
                cost_usd=0.01,
                metadata={"line": 42},
            )
            self.assertIsInstance(rid, int)
            self.assertGreater(rid, 0)

            touches = g.effects_of("agent-1")
            self.assertEqual(len(touches), 1)
            self.assertEqual(touches[0].artifact, "vault://test.md")
            self.assertEqual(touches[0].action, "written")
            self.assertEqual(touches[0].cost_usd, 0.01)
            self.assertEqual(touches[0].metadata, {"line": 42})

            causes = g.causes_of("vault://test.md")
            self.assertEqual(len(causes), 1)
            self.assertEqual(causes[0].agent_id, "agent-1")

            trace_events = g.trace_lineage("t1")
            self.assertEqual(len(trace_events), 1)
        finally:
            g.close()
            os.unlink(path)

    def test_export_formats_do_not_raise(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
            path = f.name
        g = ArtifactLineageGraph(path)
        try:
            g.record("a", "f.md", trace_id="t1")
            md = g.export_markdown()
            dot = g.export_dot()
            self.assertIn("Agent Lineage Report", md)
            self.assertIn("digraph lineage", dot)
        finally:
            g.close()
            os.unlink(path)

    def test_memory_graph_isolated(self):
        g = ArtifactLineageGraph(":memory:")
        g.record("a", "b")
        self.assertEqual(len(g.effects_of("a")), 1)
        g.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
