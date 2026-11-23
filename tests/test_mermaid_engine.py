"""Tests for ALVEA v3.0 Mermaid compiler, anti-XSS validator, and 9-type reverse parser."""

from __future__ import annotations

import unittest

from alvea.engine.mermaid import MermaidGenerator, MermaidParser, MermaidValidator
from alvea.models import (
    ActorKind,
    ActorLane,
    Direction,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
)


class TestMermaidEngineV3(unittest.TestCase):
    def setUp(self) -> None:
        self.gen = MermaidGenerator()
        self.val = MermaidValidator()
        self.parser = MermaidParser()

    def test_all_9_node_types_roundtrip_and_critical_path_highlight(self) -> None:
        graph = ProcessGraph(
            title="Full Semantic Shapes",
            lanes=[
                ActorLane(id="CUST", name="Customer", kind=ActorKind.HUMAN),
                ActorLane(id="SYS", name="Core System", kind=ActorKind.SYSTEM),
            ],
            nodes=[
                ProcessNode(id="N1", label="Start: Submit", node_type=NodeType.START, lane_id="CUST"),
                ProcessNode(id="N2", label="Call API Service", node_type=NodeType.SYSTEM, lane_id="SYS", is_automated=True),
                ProcessNode(id="N3", label="Parallel Split", node_type=NodeType.PARALLEL, lane_id="SYS", is_automated=True),
                ProcessNode(id="N4", label="Run KYC Subprocess", node_type=NodeType.SUBPROCESS, lane_id="SYS"),
                ProcessNode(id="N5", label="Wait 24h SLA", node_type=NodeType.WAIT, lane_id="CUST"),
                ProcessNode(id="N6", label="Sync / Join", node_type=NodeType.PARALLEL, lane_id="SYS", is_automated=True),
                ProcessNode(id="D1", label="Score >= 600?", node_type=NodeType.DECISION, lane_id="SYS"),
                ProcessNode(id="N7", label="Manual Review", node_type=NodeType.TASK, lane_id="CUST"),
                ProcessNode(id="E_OK", label="End: Completed", node_type=NodeType.END_SUCCESS, lane_id="CUST"),
                ProcessNode(id="E_NO", label="End: Rejected", node_type=NodeType.END_REJECT, lane_id="CUST"),
            ],
            edges=[
                ProcessEdge(source="N1", target="N2"),
                ProcessEdge(source="N2", target="N3"),
                ProcessEdge(source="N3", target="N4", label="Parallel", is_parallel=True),
                ProcessEdge(source="N3", target="N5", label="Parallel", is_parallel=True),
                ProcessEdge(source="N4", target="N6", is_parallel=True),
                ProcessEdge(source="N5", target="N6", is_parallel=True),
                ProcessEdge(source="N6", target="D1"),
                ProcessEdge(source="D1", target="N7", label="Score >= 600", is_conditional=True),
                ProcessEdge(source="D1", target="E_NO", label="Score < 600", is_conditional=True),
                ProcessEdge(source="N7", target="E_OK"),
            ],
        )

        code = self.gen.render(
            graph,
            direction=Direction.TD,
            highlight_critical=True,
            critical_path=["N1", "N2", "N3", "N5", "N6", "D1", "N7", "E_OK"],
        )
        self.assertTrue(code.startswith("graph TD"))
        self.assertIn("systemNode", code)
        self.assertIn("subprocessNode", code)
        self.assertIn("waitNode", code)
        self.assertIn("gatewayNode", code)
        self.assertIn("linkStyle", code)
        self.assertIn("≥", code)

        parsed = self.parser.parse(code, title="Full Semantic Shapes")
        parsed_types = {n.id: n.node_type for n in parsed.nodes}
        self.assertEqual(parsed_types["N2"], NodeType.SYSTEM)
        self.assertEqual(parsed_types["N4"], NodeType.SUBPROCESS)
        self.assertEqual(parsed_types["N5"], NodeType.WAIT)
        self.assertEqual(parsed_types["N3"], NodeType.PARALLEL)
        self.assertEqual(len(parsed.edges), len(graph.edges))

    def test_validator_strips_xss_and_click_directives(self) -> None:
        malicious = """```mermaid
        %%{ init: {"securityLevel": "loose"} }%%
        graph LR
        subgraph A["Admin <script>alert(1)</script>"]
            N1["<img src=x onerror=alert(1)> Review (Tier 1)"]
            N2["<details open ontoggle=alert(1)> Done"]
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
        subgraph N1["Support Desk (Tier 1)"]
            H1["Critical Incident (P1)"]:::standard
        end
        H1 --> S1[("Root Cause API (SRE)")]:::systemNode
        """
        parsed = self.parser.parse(code)
        labels = {n.id: n.label for n in parsed.nodes}
        self.assertEqual(labels["H1"], "Critical Incident (P1)")
        self.assertEqual(labels["S1"], "Root Cause API (SRE)")
        self.assertEqual(len(parsed.edges), 1)


if __name__ == "__main__":
    unittest.main()
