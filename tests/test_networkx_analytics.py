"""Pruebas del motor de analítica NetworkX y generador de Reporte Ejecutivo."""

from __future__ import annotations

import unittest

from alvea.engine.analytics import GraphAnalyzer
from alvea.engine.presets import PRESET_SCENARIOS
from alvea.engine.report import ReportBuilder
from alvea.models import (
    ActorKind,
    ActorLane,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
)


class TestNetworkXAnalytics(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = GraphAnalyzer()
        self.report_builder = ReportBuilder()

    def test_preset_compras_detects_rework_cycle_and_critical_path(self) -> None:
        graph = PRESET_SCENARIOS["compras"].graph
        analytics = self.analyzer.analyze(graph)

        self.assertEqual(analytics.lane_count, 5)
        self.assertGreaterEqual(len(analytics.cycles), 1, "Compras debe tener al menos un bucle de corrección.")
        self.assertGreaterEqual(len(analytics.critical_path), 5)
        self.assertGreater(analytics.handoff_count, 0)
        self.assertGreaterEqual(len(analytics.bottlenecks), 1)

        report = self.report_builder.build(graph, analytics)
        self.assertEqual(report.title, graph.title)
        self.assertTrue(len(report.cognitive.phase_a_actors) == 5)
        self.assertTrue(len(report.recommendations) >= 1)

    def test_structural_anomalies_detected(self) -> None:
        graph = ProcessGraph(
            title="Proceso con anomalías",
            lanes=[
                ActorLane(id="L1", name="Operaciones", kind=ActorKind.DEPARTMENT),
                ActorLane(id="L2", name="Carril Vacío", kind=ActorKind.DEPARTMENT),
            ],
            nodes=[
                ProcessNode(id="N1", label="Inicio", node_type=NodeType.START, lane_id="L1"),
                ProcessNode(id="D1", label="¿Decisión incompleta?", node_type=NodeType.DECISION, lane_id="L1"),
                ProcessNode(id="N2", label="Tarea sin salida", node_type=NodeType.TASK, lane_id="L1"),
                ProcessNode(id="N_ORPHAN", label="Nodo huérfano", node_type=NodeType.TASK, lane_id="L1"),
            ],
            edges=[
                ProcessEdge(source="N1", target="D1"),
                ProcessEdge(source="D1", target="N2", label="Sí", is_conditional=True),
            ],
        )

        analytics = self.analyzer.analyze(graph)
        kinds = {a.kind for a in analytics.anomalies}
        self.assertIn("orphan", kinds)
        self.assertIn("dead_end", kinds)
        self.assertIn("incomplete_decision", kinds)
        self.assertIn("empty_lane", kinds)


if __name__ == "__main__":
    unittest.main()
