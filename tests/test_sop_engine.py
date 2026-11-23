"""Unit tests for ALVEA v3.1 Standard Operating Procedure (SOP) Generator & Exporters."""

from __future__ import annotations

import unittest

from alvea.engine.analytics import GraphAnalyzer
from alvea.engine.nlp_parser import LocalBPAEngine
from alvea.engine.sop import SOPGenerator, render_sop_markdown
from alvea.exporters.pdf_exporter import export_sop_pdf
from alvea.models import ActorKind, ActorLane, NodeType, ProcessEdge, ProcessGraph, ProcessNode


class TestSOPEngineV31(unittest.TestCase):
    def setUp(self) -> None:
        self.nlp = LocalBPAEngine()
        self.analyzer = GraphAnalyzer()
        self.sop_gen = SOPGenerator()

    def test_parallel_fork_join_hierarchical_numbering_and_sla(self) -> None:
        workflow = (
            "Customer -> Intake Desk: Submit order request [10m]\n"
            "In parallel:\n"
            "- Legal: Review contract terms [2h]\n"
            "- IT Security: Provision sandbox access [30m]\n"
            "Wait 1h for final sign-off\n"
            "Operations: Deliver onboarding package [15m]"
        )
        graph = self.nlp.parse(workflow, title="Client Onboarding")
        analytics = self.analyzer.analyze(graph)
        sop = self.sop_gen.generate(graph, analytics)

        self.assertTrue(sop.sop_id.startswith("SOP-"))
        self.assertGreaterEqual(len(sop.steps), 6)
        self.assertGreaterEqual(len(sop.roles_and_responsibilities), 3)

        step_nums = [s.step_number for s in sop.steps]
        # Parallel branches must receive lettered hierarchical step numbers (e.g. '3a', '3b')
        self.assertTrue(any(sn.endswith("a") for sn in step_nums), f"Expected parallel track 'a' in {step_nums}")
        self.assertTrue(any(sn.endswith("b") for sn in step_nums), f"Expected parallel track 'b' in {step_nums}")

        # SLA durations must surface in steps and controls
        self.assertTrue(any(s.sla_display for s in sop.steps))
        self.assertTrue(any("SLA" in ctrl or "Critical Path" in ctrl for ctrl in sop.sla_and_controls))

    def test_rework_loop_maps_to_exact_step_number(self) -> None:
        graph = ProcessGraph(
            title="Document Review",
            lanes=[
                ActorLane(id="L_AUTH", name="Author", kind=ActorKind.HUMAN),
                ActorLane(id="L_REV", name="Reviewer", kind=ActorKind.DEPARTMENT),
            ],
            nodes=[
                ProcessNode(id="N1", label="Draft proposal", node_type=NodeType.START, lane_id="L_AUTH"),
                ProcessNode(id="N2", label="Revise draft", node_type=NodeType.TASK, lane_id="L_AUTH"),
                ProcessNode(id="N3", label="Meets quality standards?", node_type=NodeType.DECISION, lane_id="L_REV"),
                ProcessNode(id="N4", label="Publish document", node_type=NodeType.END_SUCCESS, lane_id="L_REV"),
            ],
            edges=[
                ProcessEdge(source="N1", target="N2"),
                ProcessEdge(source="N2", target="N3"),
                ProcessEdge(source="N3", target="N4", label="Approved", is_conditional=True),
                ProcessEdge(source="N3", target="N2", label="Needs Revision", is_conditional=True, is_loop=True),
            ],
        )
        analytics = self.analyzer.analyze(graph)
        sop = self.sop_gen.generate(graph, analytics)

        step_by_node = {s.node_id: s for s in sop.steps}
        self.assertEqual(step_by_node["N1"].step_number, "1")
        self.assertEqual(step_by_node["N2"].step_number, "2")
        self.assertEqual(step_by_node["N3"].step_number, "3")
        self.assertEqual(step_by_node["N4"].step_number, "4")

        decision_step = step_by_node["N3"]
        self.assertEqual(len(decision_step.rework_loops), 1)
        self.assertEqual(decision_step.rework_loops[0].target_step, "2")
        self.assertTrue(any("Return execution to Step 2" in ex or "return execution to Step 2" in ex for ex in sop.rework_and_exceptions))

    def test_markdown_sanitizes_xss_and_pdf_renders_valid_bytes(self) -> None:
        graph = ProcessGraph(
            title="Safe <script>alert(1)</script> SOP",
            lanes=[ActorLane(id="L1", name="Ops | Team", kind=ActorKind.DEPARTMENT)],
            nodes=[
                ProcessNode(id="N1", label="Start javascript:alert(1) check", node_type=NodeType.START, lane_id="L1"),
                ProcessNode(id="N2", label="Verify <img src=x onerror=alert(1)> payload", node_type=NodeType.TASK, lane_id="L1", estimated_duration_min=30.0),
                ProcessNode(id="N3", label="Completed", node_type=NodeType.END_SUCCESS, lane_id="L1"),
            ],
            edges=[
                ProcessEdge(source="N1", target="N2"),
                ProcessEdge(source="N2", target="N3"),
            ],
        )
        analytics = self.analyzer.analyze(graph)
        sop = self.sop_gen.generate(graph, analytics)

        md = render_sop_markdown(sop)
        self.assertNotIn("<script>", md.lower())
        self.assertNotIn("javascript:", md.lower())
        self.assertNotIn("<img", md.lower())
        self.assertIn("## 3. Step-by-Step Operating Procedure", md)
        self.assertIn("Ops \\| Team", md)

        pdf_bytes = export_sop_pdf(sop=sop, graph=graph)
        self.assertTrue(pdf_bytes.startswith(b"%PDF-"))
        self.assertGreater(len(pdf_bytes), 1000)


if __name__ == "__main__":
    unittest.main()
