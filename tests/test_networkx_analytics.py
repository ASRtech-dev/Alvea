"""Tests for ALVEA v3.0 NetworkX Graph Analytics & Executive Report Builder."""

from __future__ import annotations

import unittest

from alvea.engine.analytics import GraphAnalyzer
from alvea.engine.report import ReportBuilder
from alvea.models import (
    ActorKind,
    ActorLane,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
)


class TestNetworkXAnalyticsV3(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = GraphAnalyzer()
        self.report_builder = ReportBuilder()

    def test_parallel_fork_join_critical_path_picks_heavier_branch(self) -> None:
        graph = ProcessGraph(
            title="Parallel Provisioning Workflow",
            lanes=[
                ActorLane(id="OPS", name="Operations", kind=ActorKind.DEPARTMENT),
                ActorLane(id="SYS", name="API Platform", kind=ActorKind.SYSTEM),
                ActorLane(id="LEG", name="Legal", kind=ActorKind.DEPARTMENT),
            ],
            nodes=[
                ProcessNode(id="N_START", label="Start: Order Received", node_type=NodeType.START, lane_id="OPS", duration_weight=5.0, estimated_duration_min=5.0),
                ProcessNode(id="N_FORK", label="Parallel Split", node_type=NodeType.PARALLEL, lane_id="OPS", is_automated=True, duration_weight=0.5, estimated_duration_min=0.5),
                ProcessNode(id="N_FAST", label="Sync CRM via API", node_type=NodeType.SYSTEM, lane_id="SYS", is_automated=True, duration_weight=10.0, estimated_duration_min=10.0),
                ProcessNode(id="N_SLOW", label="Wait for Legal Sign-Off", node_type=NodeType.WAIT, lane_id="LEG", duration_weight=120.0, estimated_duration_min=120.0),
                ProcessNode(id="N_JOIN", label="Sync / Join", node_type=NodeType.PARALLEL, lane_id="OPS", is_automated=True, duration_weight=0.5, estimated_duration_min=0.5),
                ProcessNode(id="N_END", label="End: Provisioned", node_type=NodeType.END_SUCCESS, lane_id="OPS", is_automated=True, duration_weight=1.0, estimated_duration_min=1.0),
            ],
            edges=[
                ProcessEdge(source="N_START", target="N_FORK"),
                ProcessEdge(source="N_FORK", target="N_FAST", label="Parallel", is_parallel=True),
                ProcessEdge(source="N_FORK", target="N_SLOW", label="Parallel", is_parallel=True),
                ProcessEdge(source="N_FAST", target="N_JOIN", is_parallel=True),
                ProcessEdge(source="N_SLOW", target="N_JOIN", is_parallel=True),
                ProcessEdge(source="N_JOIN", target="N_END"),
            ],
        )

        analytics = self.analyzer.analyze(graph)
        # Critical path must follow N_SLOW (120m), NOT sum N_FAST (10m) + N_SLOW (120m)
        self.assertIn("N_SLOW", analytics.critical_path)
        self.assertNotIn("N_FAST", analytics.critical_path)
        self.assertEqual(analytics.duration_unit, "min")
        self.assertAlmostEqual(analytics.estimated_cycle_time_min or 0.0, 127.0, places=1)
        self.assertEqual(analytics.anomalies, [], "Parallel/system/wait nodes must not trigger false anomalies.")
        self.assertEqual(analytics.parallel_count, 2)
        self.assertEqual(analytics.wait_count, 1)
        self.assertEqual(analytics.system_count, 1)

        report = self.report_builder.build(graph, analytics)
        self.assertTrue(any(r.category == "SLA & Wait Optimization" for r in report.recommendations))

    def test_structural_anomalies_and_rework_cycle_detected(self) -> None:
        graph = ProcessGraph(
            title="Anomaly & Rework Check",
            lanes=[
                ActorLane(id="L1", name="Operations", kind=ActorKind.DEPARTMENT),
                ActorLane(id="L2", name="Unused Lane", kind=ActorKind.DEPARTMENT),
            ],
            nodes=[
                ProcessNode(id="N1", label="Start", node_type=NodeType.START, lane_id="L1"),
                ProcessNode(id="N2", label="Review", node_type=NodeType.TASK, lane_id="L1"),
                ProcessNode(id="D1", label="Incomplete Check?", node_type=NodeType.DECISION, lane_id="L1"),
                ProcessNode(id="N3", label="Fix & Resubmit", node_type=NodeType.TASK, lane_id="L1"),
                ProcessNode(id="N_DEAD", label="Dangling Task", node_type=NodeType.TASK, lane_id="L1"),
                ProcessNode(id="N_ORPHAN", label="Orphan Node", node_type=NodeType.TASK, lane_id="L1"),
            ],
            edges=[
                ProcessEdge(source="N1", target="N2"),
                ProcessEdge(source="N2", target="D1"),
                ProcessEdge(source="D1", target="N3", label="Rejected", is_conditional=True),
                ProcessEdge(source="N3", target="N2", label="Retry", is_loop=True),
                ProcessEdge(source="N2", target="N_DEAD"),
            ],
        )

        analytics = self.analyzer.analyze(graph)
        kinds = {a.kind for a in analytics.anomalies}
        self.assertIn("orphan", kinds)
        self.assertIn("dead_end", kinds)
        self.assertIn("incomplete_decision", kinds)
        self.assertIn("empty_lane", kinds)
        self.assertGreaterEqual(len(analytics.cycles), 1)
        self.assertIn(analytics.complexity_level, ("Low", "Moderate", "High"))


if __name__ == "__main__":
    unittest.main()
