"""Pruebas del Motor Nativo Python BPA (parser NLP determinista ES/EN)."""

from __future__ import annotations

import unittest

from alvea.engine.nlp_parser import LocalBPAEngine
from alvea.models import Direction, NodeType


class TestLocalBPAEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = LocalBPAEngine()

    def test_spanish_free_text_with_decision_and_rework_loop(self) -> None:
        text = (
            "Un empleado solicita un reembolso en el portal. "
            "El supervisor revisa las facturas. "
            "Si hay inconsistencias, el supervisor devuelve la solicitud al empleado para corregir comprobantes. "
            "Si el supervisor aprueba, contabilidad programa la transferencia y finaliza el pago."
        )
        graph = self.engine.parse(text, direction=Direction.LR)

        self.assertGreaterEqual(len(graph.lanes), 3)
        self.assertTrue(any(n.node_type == NodeType.START for n in graph.nodes))
        self.assertTrue(any(n.node_type == NodeType.DECISION for n in graph.nodes))
        self.assertTrue(any(n.node_type == NodeType.END_SUCCESS for n in graph.nodes))
        self.assertTrue(any(e.is_loop for e in graph.edges), "Debe detectar bucle de retrabajo.")

    def test_english_process_with_branches(self) -> None:
        text = (
            "A customer submits a loan request in the mobile app. "
            "The system checks credit score automatically. "
            "If the score is below 600, the system rejects the request. "
            "Otherwise, the risk analyst approves the income and legal issues the contract."
        )
        graph = self.engine.parse(text, direction=Direction.TD)

        self.assertEqual(graph.language, "en")
        self.assertEqual(graph.direction, Direction.TD)
        decisions = [n for n in graph.nodes if n.node_type == NodeType.DECISION]
        self.assertGreaterEqual(len(decisions), 1)
        # Cada decisión debe tener al menos 2 ramas salientes
        for dec in decisions:
            out_edges = [e for e in graph.edges if e.source == dec.id]
            self.assertGreaterEqual(len(out_edges), 2)

    def test_open_domain_actors_and_special_chars(self) -> None:
        text = (
            "El Médico de Triaje evalúa signos vitales en 10 minutos. "
            "Si el paciente presenta riesgo alto, escala al Comité de Urgencias. "
            "De lo contrario, deriva a consulta externa y finaliza atención."
        )
        graph = self.engine.parse(text)
        lane_names = [ln.name.lower() for ln in graph.lanes]
        self.assertTrue(any("triaje" in name or "médico" in name or "medico" in name for name in lane_names))
        self.assertTrue(any(n.estimated_duration_min == 10.0 for n in graph.nodes))

    def test_single_sentence_fallback(self) -> None:
        graph = self.engine.parse("Registrar pedido y emitir factura final.")
        self.assertGreaterEqual(len(graph.nodes), 2)
        self.assertGreaterEqual(len(graph.edges), 1)


if __name__ == "__main__":
    unittest.main()
