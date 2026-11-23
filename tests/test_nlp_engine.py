"""Tests for ALVEA v3.0 Native Python Workflow Engine (multi-format, fork/join, multi-branch, SLAs, anti-ReDoS)."""

from __future__ import annotations

import time
import unittest

from alvea.engine.nlp_parser import LocalBPAEngine
from alvea.models import Direction, NodeType


class TestWorkflowEngineV3(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = LocalBPAEngine()

    def test_arrow_and_actor_action_notation_with_durations(self) -> None:
        text = """
        Customer -> API Gateway: Submit onboarding application [5m]
        API Gateway: Run KYC subprocess automatically [10m]
        Wait 2h for external compliance confirmation
        Finance: Approve account activation [30m]
        """
        graph = self.engine.parse(text, direction=Direction.LR)
        types = {n.node_type for n in graph.nodes}
        self.assertIn(NodeType.START, types)
        self.assertIn(NodeType.SUBPROCESS, types)
        self.assertIn(NodeType.WAIT, types)
        self.assertIn(NodeType.END_SUCCESS, types)
        self.assertTrue(any(n.estimated_duration_min == 120.0 for n in graph.nodes))
        self.assertGreaterEqual(len(graph.lanes), 3)

    def test_parallel_fork_join_block(self) -> None:
        text = """
        Customer: Submit signed order [10m]
        In parallel:
        - Legal: Archive compliance record [30m]
        - IT Operations: Provision cloud workspace via API [2h]
        Finance: Issue final invoice [15m]
        """
        graph = self.engine.parse(text)
        parallel_nodes = [n for n in graph.nodes if n.node_type == NodeType.PARALLEL]
        self.assertGreaterEqual(len(parallel_nodes), 2, "Must create both Fork and Join parallel gateways.")
        fork_node = parallel_nodes[0]
        join_node = parallel_nodes[-1]
        self.assertGreaterEqual(sum(1 for e in graph.edges if e.source == fork_node.id), 2)
        self.assertGreaterEqual(sum(1 for e in graph.edges if e.target == join_node.id), 2)

    def test_multi_branch_if_elif_else_decision(self) -> None:
        text = (
            "Employee: Submit expense report. "
            "If amount > 10000, Finance approves the budget. "
            "Else if amount > 1000, Manager approves the expense. "
            "Otherwise, System auto-approves the expense."
        )
        graph = self.engine.parse(text, direction=Direction.TD)
        self.assertEqual(graph.direction, Direction.TD)
        decisions = [n for n in graph.nodes if n.node_type == NodeType.DECISION]
        self.assertEqual(len(decisions), 1)
        out_edges = [e for e in graph.edges if e.source == decisions[0].id]
        self.assertGreaterEqual(len(out_edges), 3, "If / Else if / Otherwise must attach 3+ branches to the same decision.")

    def test_spanish_rework_loop_and_bilingual_support(self) -> None:
        text = (
            "Un empleado solicita un reembolso en el portal. "
            "El supervisor revisa las facturas. "
            "Si hay inconsistencias, el supervisor devuelve la solicitud al empleado para corregir comprobantes. "
            "Si el supervisor aprueba, contabilidad programa la transferencia y finaliza el pago."
        )
        graph = self.engine.parse(text)
        self.assertEqual(graph.language, "es")
        self.assertTrue(any(e.is_loop for e in graph.edges))

    def test_anti_redos_performance_on_adversarial_15k_input(self) -> None:
        adversarial = ("Actor A -> Actor B: Check item -> sub -> step [10m]\n" * 280)[:14_900]
        t0 = time.perf_counter()
        graph = self.engine.parse(adversarial)
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 0.5, f"Parser too slow on 15k input: {elapsed:.3f}s")
        self.assertLessEqual(len(graph.nodes), 80)
        self.assertLessEqual(len(graph.edges), 200)


if __name__ == "__main__":
    unittest.main()
