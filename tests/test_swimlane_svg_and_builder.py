"""Tests for ALVEA v4.0 True BPMN Swimlane SVG Engine & Visual Builder API (/api/v1/graph/build)."""

from __future__ import annotations

import threading
import time
import unittest
import xml.etree.ElementTree as ET

import httpx

from alvea.engine.analytics import GraphAnalyzer
from alvea.engine.swimlane_svg import MAX_SVG_HEIGHT, MAX_SVG_WIDTH, SwimlaneSVGRenderer
from alvea.models import ActorKind, ActorLane, Direction, NodeType, ProcessEdge, ProcessGraph, ProcessNode
from alvea.server.app import create_server


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


class TestSwimlaneSVGAndVisualBuilder(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def _build_support_workflow(self) -> ProcessGraph:
        return ProcessGraph(
            title="Customer Support Email Resolution",
            direction=Direction.LR,
            lanes=[
                ActorLane(id="L_CUST", name="Customer", kind=ActorKind.HUMAN, order=0),
                ActorLane(id="L_SYS", name="System", kind=ActorKind.SYSTEM, order=1),
                ActorLane(id="L_CS", name="Customer Service", kind=ActorKind.DEPARTMENT, order=2),
                ActorLane(id="L_BO", name="Back-Office Team", kind=ActorKind.DEPARTMENT, order=3),
            ],
            nodes=[
                ProcessNode(id="N1", label="Submit Email Request", node_type=NodeType.START, lane_id="L_CUST"),
                ProcessNode(id="N2", label="Categorize & Route Email", node_type=NodeType.SYSTEM, lane_id="L_SYS", is_automated=True, estimated_duration_min=1.0),
                ProcessNode(id="N3", label="Review Email & Assess", node_type=NodeType.TASK, lane_id="L_CS", estimated_duration_min=15.0),
                ProcessNode(id="N4", label="Solve Directly?", node_type=NodeType.DECISION, lane_id="L_CS"),
                ProcessNode(id="N5", label="Solve Problem Directly", node_type=NodeType.TASK, lane_id="L_CS", estimated_duration_min=30.0),
                ProcessNode(id="N6", label="Escalate to Back-Office", node_type=NodeType.TASK, lane_id="L_CS", estimated_duration_min=10.0),
                ProcessNode(id="N7", label="Resolve Escalated Case", node_type=NodeType.TASK, lane_id="L_BO", estimated_duration_min=3600.0),
                ProcessNode(id="N8", label="Send Confirmation", node_type=NodeType.SYSTEM, lane_id="L_SYS", is_automated=True, estimated_duration_min=1.0),
                ProcessNode(id="N9", label="Case Resolved Successfully", node_type=NodeType.END_SUCCESS, lane_id="L_CUST"),
            ],
            edges=[
                ProcessEdge(source="N1", target="N2"),
                ProcessEdge(source="N2", target="N3"),
                ProcessEdge(source="N3", target="N4"),
                ProcessEdge(source="N4", target="N5", label="Yes", is_conditional=True),
                ProcessEdge(source="N4", target="N6", label="No", is_conditional=True),
                ProcessEdge(source="N5", target="N8"),
                ProcessEdge(source="N6", target="N7"),
                ProcessEdge(source="N7", target="N8"),
                ProcessEdge(source="N8", target="N9"),
            ],
        )

    def test_start_is_far_left_and_same_lane_end_is_far_right(self) -> None:
        graph = self._build_support_workflow()
        analytics = GraphAnalyzer().analyze(graph)
        svg = SwimlaneSVGRenderer().render(graph, analytics=analytics, direction=Direction.LR, highlight_critical=True)

        root = ET.fromstring(svg)
        self.assertEqual(_strip_ns(root.tag), "svg")

        # Extract x-center of every rendered node from its child shape/text x coordinate
        node_x: dict[str, float] = {}
        for g in root.iter():
            if _strip_ns(g.tag) == "g" and g.attrib.get("data-node-id"):
                nid = g.attrib["data-node-id"]
                for child in g:
                    if _strip_ns(child.tag) == "text" and "x" in child.attrib:
                        node_x[nid] = float(child.attrib["x"])
                        break

        self.assertIn("N1", node_x)
        self.assertIn("N9", node_x)
        # Start (N1, Customer lane) MUST be leftmost; End (N9, ALSO Customer lane) MUST be rightmost!
        self.assertEqual(node_x["N1"], min(node_x.values()))
        self.assertEqual(node_x["N9"], max(node_x.values()))
        self.assertGreater(node_x["N9"], node_x["N7"])
        self.assertGreater(node_x["N7"], node_x["N4"])
        self.assertGreater(node_x["N4"], node_x["N2"])
        self.assertGreater(node_x["N2"], node_x["N1"])

        # Vertical TD mode must also emit valid XML
        svg_td = SwimlaneSVGRenderer().render(graph, analytics=analytics, direction=Direction.TD)
        self.assertEqual(_strip_ns(ET.fromstring(svg_td).tag), "svg")

    def test_svg_renderer_blocks_xss_and_forbidden_tags(self) -> None:
        graph = ProcessGraph(
            title='Attack <script>alert(1)</script> "><svg onload=alert(1)>',
            lanes=[ActorLane(id="L1", name='<foreignObject>Evil</foreignObject> Ops', kind=ActorKind.DEPARTMENT)],
            nodes=[
                ProcessNode(id="N1", label="Start javascript:alert(1)", node_type=NodeType.START, lane_id="L1"),
                ProcessNode(id="N2", label='<img src=x onerror="alert(1)"> Check', node_type=NodeType.DECISION, lane_id="L1"),
                ProcessNode(id="N3", label="Done", node_type=NodeType.END_SUCCESS, lane_id="L1"),
            ],
            edges=[
                ProcessEdge(source="N1", target="N2", label='<script>x</script>'),
                ProcessEdge(source="N2", target="N3", label="Yes", is_conditional=True),
            ],
        )
        svg = SwimlaneSVGRenderer().render(graph)
        root = ET.fromstring(svg)

        forbidden_tags = {"script", "foreignobject", "iframe", "object", "embed", "animate", "set", "use"}
        for elem in root.iter():
            tag = _strip_ns(elem.tag).lower()
            self.assertNotIn(tag, forbidden_tags)
            for attr_name, attr_val in elem.attrib.items():
                self.assertFalse(attr_name.lower().startswith("on"))
                self.assertNotIn("javascript:", attr_val.lower())

    def test_visual_builder_api_cyclic_anti_dos_and_validation_limits(self) -> None:
        with httpx.Client(base_url=self.base_url) as client:
            # 1. Valid Visual Builder workflow with True/False + Rework loop
            payload = {
                "title": "Dropdown Built Support Flow",
                "direction": "LR",
                "highlight_critical": True,
                "lanes": [
                    {"id": "L_1", "name": "Customer", "kind": "human", "order": 0},
                    {"id": "L_2", "name": "Support", "kind": "department", "order": 1},
                ],
                "nodes": [
                    {"id": "S_1", "label": "Submit Request", "node_type": "start", "lane_id": "L_1"},
                    {"id": "S_2", "label": "Review Ticket", "node_type": "task", "lane_id": "L_2", "estimated_duration_min": 15.0},
                    {"id": "S_3", "label": "Solved?", "node_type": "decision", "lane_id": "L_2"},
                    {"id": "S_4", "label": "Case Resolved", "node_type": "end_success", "lane_id": "L_1"},
                ],
                "edges": [
                    {"source": "S_1", "target": "S_2"},
                    {"source": "S_2", "target": "S_3"},
                    {"source": "S_3", "target": "S_4", "label": "Yes", "is_conditional": True},
                    {"source": "S_3", "target": "S_2", "label": "Rework", "is_conditional": True, "is_loop": True},
                ],
            }
            resp = client.post("/api/v1/graph/build", json=payload)
            self.assertEqual(resp.status_code, 200)
            self.assertEqual(resp.headers.get("x-content-type-options"), "nosniff")
            self.assertIn("no-store", resp.headers.get("cache-control", ""))
            body = resp.json()
            self.assertIn("swimlane_svg", body)
            self.assertIn("sop", body)
            self.assertIn("mermaid", body)
            root = ET.fromstring(body["swimlane_svg"])
            self.assertLessEqual(float(root.attrib["width"]), MAX_SVG_WIDTH)
            self.assertLessEqual(float(root.attrib["height"]), MAX_SVG_HEIGHT)

            # 2. Highly cyclic anti-DoS test (< 0.5s)
            cyc_nodes = [
                {"id": f"C_{i}", "label": f"Step {i}", "node_type": "task", "lane_id": "L_1"}
                for i in range(1, 21)
            ]
            cyc_edges = [{"source": f"C_{i}", "target": f"C_{(i % 20) + 1}"} for i in range(1, 21)]
            t0 = time.perf_counter()
            cyc_resp = client.post(
                "/api/v1/graph/build",
                json={
                    "title": "Cyclic Stress",
                    "lanes": [{"id": "L_1", "name": "Ops", "kind": "department"}],
                    "nodes": cyc_nodes,
                    "edges": cyc_edges,
                },
            )
            elapsed = time.perf_counter() - t0
            self.assertEqual(cyc_resp.status_code, 200)
            self.assertLess(elapsed, 0.5)

            # 3. Validation bounds: >16 lanes -> 422, oversized -> 413
            too_many_lanes = [{"id": f"L_{i}", "name": f"Team {i}", "kind": "department"} for i in range(20)]
            bad_resp = client.post(
                "/api/v1/graph/build",
                json={
                    "title": "Too Many",
                    "lanes": too_many_lanes,
                    "nodes": [{"id": "N1", "label": "Start", "node_type": "start", "lane_id": "L_1"}],
                    "edges": [],
                },
            )
            self.assertEqual(bad_resp.status_code, 422)

            big_resp = client.post(
                "/api/v1/graph/build",
                json={"title": "A" * 70_000, "lanes": [], "nodes": [], "edges": []},
            )
            self.assertEqual(big_resp.status_code, 413)


if __name__ == "__main__":
    unittest.main()
