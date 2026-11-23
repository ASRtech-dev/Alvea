"""Pruebas del compilador, validador/reparador anti-XSS y parser inverso de Mermaid."""

from __future__ import annotations

import unittest

from alvea.engine.mermaid import MermaidGenerator, MermaidParser, MermaidValidator
from alvea.engine.presets import PRESET_SCENARIOS
from alvea.models import Direction


class TestMermaidEngine(unittest.TestCase):
    def setUp(self) -> None:
        self.gen = MermaidGenerator()
        self.val = MermaidValidator()
        self.parser = MermaidParser()

    def test_generator_supports_lr_td_and_critical_path(self) -> None:
        graph = PRESET_SCENARIOS["credito"].graph
        lr_code = self.gen.render(graph, direction=Direction.LR)
        td_code = self.gen.render(
            graph,
            direction=Direction.TD,
            highlight_critical=True,
            critical_path=["C1", "S1", "D1", "R1"],
        )
        self.assertTrue(lr_code.startswith("graph LR"))
        self.assertTrue(td_code.startswith("graph TD"))
        self.assertIn("linkStyle", td_code)
        self.assertIn("criticalNode", td_code)

    def test_validator_strips_xss_and_click_directives(self) -> None:
        malicious = """```mermaid
        %%{ init: {"securityLevel": "loose"} }%%
        graph LR
        subgraph A["Área <script>alert(1)</script>"]
            N1["<img src=x onerror=alert(1)> Revisar (Nivel 1)"]
            N2["<details open ontoggle=alert(1)> Fin"]
        click N1 "javascript:alert(1)"
        N1 --> N2; click N2 href "https://evil.example"
        ```"""
        res = self.val.validate_and_repair(malicious)
        self.assertTrue(res.is_valid)
        self.assertNotIn("click ", res.repaired_code)
        self.assertNotIn("securityLevel", res.repaired_code)
        self.assertNotIn("<script>", res.repaired_code.lower())
        self.assertNotIn("onerror", res.repaired_code.lower())
        self.assertNotIn("ontoggle", res.repaired_code.lower())
        self.assertNotIn("javascript:", res.repaired_code.lower())
        self.assertIn("end", res.repaired_code)

    def test_parser_preserves_parentheses_labels_and_inline_edges(self) -> None:
        code = """graph LR
        subgraph N1["Mesa de Ayuda (Nivel 1)"]
            H1["Incidente crítico (P1)"]:::standard
        end
        H1 --> S1["Diagnóstico (SRE)"]
        """
        parsed = self.parser.parse(code)
        labels = {n.id: n.label for n in parsed.nodes}
        self.assertEqual(labels["H1"], "Incidente crítico (P1)")
        self.assertEqual(labels["S1"], "Diagnóstico (SRE)")
        self.assertEqual(len(parsed.edges), 1)

    def test_reverse_parser_roundtrip(self) -> None:
        graph = PRESET_SCENARIOS["viaticos"].graph
        mermaid_code = self.gen.render(graph)
        parsed = self.parser.parse(mermaid_code, title="Viáticos")
        self.assertEqual(len(parsed.lanes), len(graph.lanes))
        self.assertEqual(len(parsed.nodes), len(graph.nodes))
        self.assertEqual(len(parsed.edges), len(graph.edges))


if __name__ == "__main__":
    unittest.main()
