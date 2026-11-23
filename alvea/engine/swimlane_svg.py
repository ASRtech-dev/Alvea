"""ALVEA v4.0 Native Python BPMN 2.0 Swimlane SVG Layout Engine.

Renders true executive BPMN Swimlane diagrams directly from ProcessGraph + GraphAnalytics:
  - Horizontal full-width swimlane rows stacked vertically (LR) or vertical columns (TD)
  - Strict Left -> Right (or Top -> Bottom) topological column assignment over condensed DAG
  - START nodes always pinned to Column 0 (far left); terminal END nodes always pinned to max_col (far right)
  - Dynamic sub-rows inside each (lane, column) cell guaranteeing zero overlapping nodes
  - Orthogonal Manhattan routing with rounded Q-Bezier corners, dedicated gutters, and dashed rework loops
  - Pure SVG vector primitives + <text><tspan> ONLY (ZERO <foreignObject>, ZERO <script>, strict XML escaping)
"""

from __future__ import annotations

import math
import re
from xml.sax.saxutils import escape as xml_escape

import networkx as nx

from alvea.engine.analytics import GraphAnalyzer
from alvea.models import (
    Direction,
    GraphAnalytics,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
    sanitize_label_text,
)

# Deterministic executive accent palette synced with Visual Builder team chips
LANE_ACCENT_PALETTE: tuple[str, ...] = (
    "#1E3A5F",  # Deep Navy
    "#0284C7",  # Sky Blue
    "#0D9488",  # Teal
    "#4338CA",  # Indigo
    "#B45309",  # Amber Ochre
    "#7C3AED",  # Royal Violet
    "#BE123C",  # Crimson Rose
    "#334155",  # Executive Slate
)

_XML_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

MAX_SVG_WIDTH = 8000
MAX_SVG_HEIGHT = 6000


def _xml_safe(raw: str, max_len: int = 96) -> str:
    """Sanitizes user text and escapes all XML/attribute special characters."""
    cleaned = _XML_CTRL_RE.sub("", str(raw or ""))
    cleaned = sanitize_label_text(cleaned, max_len=max_len)
    return xml_escape(cleaned, {'"': "&quot;", "'": "&#39;"})


def _wrap_lines(text: str, max_chars: int = 20, max_lines: int = 3) -> list[str]:
    """Deterministic word-wrapper producing short lines safe for SVG <tspan>."""
    cleaned = sanitize_label_text(text, max_len=96)
    words = cleaned.split()
    if not words:
        return ["Step"]
    lines: list[str] = []
    cur = ""
    for word in words:
        if len(word) > max_chars:
            if cur:
                lines.append(cur)
                cur = ""
            lines.append(word[: max_chars - 1] + "...")
        elif not cur:
            cur = word
        elif len(cur) + 1 + len(word) <= max_chars:
            cur = f"{cur} {word}"
        else:
            lines.append(cur)
            cur = word
        if len(lines) >= max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and len(" ".join(words)) > sum(len(x) for x in lines) + max_lines:
        if not lines[-1].endswith("..."):
            lines[-1] = lines[-1][: max(1, max_chars - 3)].rstrip() + "..."
    return lines[:max_lines]


def _format_sla_badge(minutes: float | None) -> str | None:
    if minutes is None or minutes <= 0:
        return None
    if minutes >= 1440:
        days = minutes / 1440.0
        return f"{int(round(days))}d" if abs(days - round(days)) < 0.08 else f"{days:.1f}d"
    if minutes >= 60:
        hrs = minutes / 60.0
        return f"{int(round(hrs))}h" if abs(hrs - round(hrs)) < 0.08 else f"{hrs:.1f}h"
    if minutes < 1:
        return f"{int(round(minutes * 60))}s"
    return f"{int(round(minutes))}m"


def _fmt(val: float) -> str:
    if not math.isfinite(val):
        return "0"
    return f"{val:.1f}".rstrip("0").rstrip(".")


def _rounded_ortho_path(points: list[tuple[float, float]], radius: float = 8.0) -> str:
    """Converts a polyline into an SVG path with smooth rounded quadratic corners."""
    # Deduplicate consecutive identical points and collinear midpoints
    pts: list[tuple[float, float]] = []
    for p in points:
        if not pts or abs(p[0] - pts[-1][0]) > 0.5 or abs(p[1] - pts[-1][1]) > 0.5:
            pts.append(p)
    if len(pts) < 2:
        return ""
    if len(pts) == 2:
        return f"M {_fmt(pts[0][0])} {_fmt(pts[0][1])} L {_fmt(pts[1][0])} {_fmt(pts[1][1])}"

    cmds: list[str] = [f"M {_fmt(pts[0][0])} {_fmt(pts[0][1])}"]
    for idx in range(1, len(pts) - 1):
        p_prev = pts[idx - 1]
        p_cur = pts[idx]
        p_next = pts[idx + 1]
        vx1, vy1 = p_cur[0] - p_prev[0], p_cur[1] - p_prev[1]
        vx2, vy2 = p_next[0] - p_cur[0], p_next[1] - p_cur[1]
        len1 = math.hypot(vx1, vy1)
        len2 = math.hypot(vx2, vy2)
        if len1 < 1.0 or len2 < 1.0:
            cmds.append(f"L {_fmt(p_cur[0])} {_fmt(p_cur[1])}")
            continue
        r = min(radius, len1 * 0.45, len2 * 0.45)
        sx = p_cur[0] - (vx1 / len1) * r
        sy = p_cur[1] - (vy1 / len1) * r
        ex = p_cur[0] + (vx2 / len2) * r
        ey = p_cur[1] + (vy2 / len2) * r
        cmds.append(f"L {_fmt(sx)} {_fmt(sy)} Q {_fmt(p_cur[0])} {_fmt(p_cur[1])} {_fmt(ex)} {_fmt(ey)}")

    cmds.append(f"L {_fmt(pts[-1][0])} {_fmt(pts[-1][1])}")
    return " ".join(cmds)


def _edge_pill_style(label: str, is_loop: bool) -> tuple[str, str, str]:
    """Returns (fill, stroke, text_color) for an edge pill label."""
    if is_loop:
        return ("#FEF2F2", "#FCA5A5", "#B91C1C")
    low = label.lower()
    if any(w in low for w in ("yes", "true", "approv", "valid", "solv", "ok", "pass", "sí", "si", "acept", "resuelv")):
        return ("#ECFDF5", "#6EE7B7", "#047857")
    if any(w in low for w in ("no", "false", "reject", "deni", "escalat", "fail", "invalid", "rework", "rechaz", "escal")):
        return ("#FFFBEB", "#FCD34D", "#B45309")
    return ("#FFFFFF", "#CBD5E1", "#334155")


class SwimlaneSVGRenderer:
    """Executive BPMN 2.0 Swimlane SVG generator backed by NetworkX DAG layering."""

    def render(
        self,
        graph: ProcessGraph,
        *,
        analytics: GraphAnalytics | None = None,
        direction: Direction | None = None,
        highlight_critical: bool = False,
        align_ends_right: bool = True,
    ) -> str:
        target_dir = direction or graph.direction
        if target_dir == Direction.TD:
            return self._render_vertical_td(
                graph,
                analytics=analytics,
                highlight_critical=highlight_critical,
                align_ends_right=align_ends_right,
            )
        return self._render_horizontal_lr(
            graph,
            analytics=analytics,
            highlight_critical=highlight_critical,
            align_ends_right=align_ends_right,
        )

    # ─── Core Topological Layering (Shared by LR & TD) ─────────────────────────

    @staticmethod
    def _compute_dag_and_layers(
        graph: ProcessGraph,
        *,
        align_ends_right: bool,
    ) -> tuple[nx.DiGraph, dict[str, int], set[tuple[str, str]]]:
        G = nx.DiGraph()
        node_by_id = {n.id: n for n in graph.nodes}
        for n in graph.nodes:
            G.add_node(n.id)
        for e in graph.edges:
            if e.source in node_by_id and e.target in node_by_id and e.source != e.target:
                G.add_edge(e.source, e.target)

        back_edges = GraphAnalyzer._find_dfs_back_edges(G, graph)

        G_dag = G.copy()
        for u, v in list(back_edges):
            if G_dag.has_edge(u, v):
                G_dag.remove_edge(u, v)

        safety = 0
        while not nx.is_directed_acyclic_graph(G_dag) and safety < 80:
            safety += 1
            try:
                cyc = nx.find_cycle(G_dag, orientation="original")
                u, v, _ = cyc[-1]
                G_dag.remove_edge(u, v)
                back_edges.add((u, v))
            except nx.NetworkXNoCycle:
                break

        col: dict[str, int] = {}
        try:
            topo = list(nx.topological_sort(G_dag))
        except nx.NetworkXUnfeasible:
            topo = [n.id for n in graph.nodes]

        for nid in topo:
            node = node_by_id[nid]
            preds = list(G_dag.predecessors(nid))
            if node.node_type == NodeType.START or not preds:
                col[nid] = 0
            else:
                col[nid] = max(col.get(p, 0) + 1 for p in preds)

        if align_ends_right and col:
            non_end_cols = [
                c
                for nid, c in col.items()
                if node_by_id[nid].node_type not in (NodeType.END_SUCCESS, NodeType.END_REJECT)
            ]
            max_non_end = max(non_end_cols, default=0)
            terminal_col = max(max_non_end + 1, max(col.values()))
            for nid in topo:
                nt = node_by_id[nid].node_type
                if nt in (NodeType.END_SUCCESS, NodeType.END_REJECT) and G_dag.out_degree(nid) == 0:
                    col[nid] = terminal_col

        return G_dag, col, back_edges

    # ─── Horizontal Swimlanes (LR: Rows = Lanes, Columns = Left -> Right) ──────

    def _render_horizontal_lr(
        self,
        graph: ProcessGraph,
        *,
        analytics: GraphAnalytics | None,
        highlight_critical: bool,
        align_ends_right: bool,
    ) -> str:
        node_by_id = {n.id: n for n in graph.nodes}
        node_idx = {n.id: idx for idx, n in enumerate(graph.nodes)}
        G_dag, col, back_edges = self._compute_dag_and_layers(graph, align_ends_right=align_ends_right)

        critical_nodes = set(analytics.critical_path) if (analytics and highlight_critical) else set()
        critical_edges: set[tuple[str, str]] = set()
        if analytics and highlight_critical and len(analytics.critical_path) >= 2:
            for a, b in zip(analytics.critical_path, analytics.critical_path[1:]):
                critical_edges.add((a, b))

        # Keep user/LLM lane order (already top-down) while ensuring every lane with nodes appears
        ordered_lanes = sorted(graph.lanes, key=lambda ln: ln.order)
        lane_row_idx = {ln.id: idx for idx, ln in enumerate(ordered_lanes)}
        lane_accent = {
            ln.id: LANE_ACCENT_PALETTE[idx % len(LANE_ACCENT_PALETTE)]
            for idx, ln in enumerate(ordered_lanes)
        }

        num_cols = max(col.values(), default=0) + 1

        # Group nodes by (lane_id, col) and sort within cell to minimize edge crossings
        cells: dict[tuple[str, int], list[str]] = {}
        for n in graph.nodes:
            key = (n.lane_id, col.get(n.id, 0))
            cells.setdefault(key, []).append(n.id)

        for key, nids in cells.items():
            if len(nids) > 1:
                def _cell_order(nid: str) -> tuple[int, float, int]:
                    preds = list(G_dag.predecessors(nid))
                    avg_r = (
                        sum(lane_row_idx.get(node_by_id[p].lane_id, 0) for p in preds) / len(preds)
                        if preds
                        else float(lane_row_idx.get(node_by_id[nid].lane_id, 0))
                    )
                    return (0 if nid in critical_nodes else 1, avg_r, node_idx.get(nid, 999))
                nids.sort(key=_cell_order)

        # Calibrated executive dimensions
        PAD_X = 24.0
        PAD_TOP = 54.0
        PAD_BOTTOM = 44.0
        HEADER_W = 168.0
        COL_W = 240.0
        NODE_W = 168.0
        NODE_H = 62.0
        SUBROW_H = 92.0
        LANE_PAD_Y = 28.0

        # Dynamic height per lane so multiple stacked nodes NEVER overlap
        lane_bounds: dict[str, tuple[float, float]] = {}
        cur_y = PAD_TOP
        for ln in ordered_lanes:
            max_stack = max(
                (len(cells.get((ln.id, c), [])) for c in range(num_cols)),
                default=1,
            )
            max_stack = max(1, max_stack)
            lh = max(124.0, max_stack * SUBROW_H + 2.0 * LANE_PAD_Y)
            lane_bounds[ln.id] = (cur_y, cur_y + lh)
            cur_y += lh

        content_right = PAD_X + HEADER_W + num_cols * COL_W + 24.0
        total_w = min(float(MAX_SVG_WIDTH), max(780.0, content_right + PAD_X))
        total_h = min(float(MAX_SVG_HEIGHT), cur_y + PAD_BOTTOM)

        # Compute exact node bounding boxes (cx, cy, w, h)
        node_box: dict[str, tuple[float, float, float, float]] = {}
        for (lid, c), nids in cells.items():
            y0, y1 = lane_bounds[lid]
            lane_h = y1 - y0
            cx = PAD_X + HEADER_W + c * COL_W + (COL_W - 44.0) * 0.5 + 14.0
            stack_h = len(nids) * SUBROW_H
            start_cy = y0 + (lane_h - stack_h) * 0.5 + SUBROW_H * 0.5
            for k, nid in enumerate(nids):
                cy = start_cy + k * SUBROW_H
                nt = node_by_id[nid].node_type
                if nt == NodeType.DECISION:
                    w, h = 152.0, 74.0
                elif nt in (NodeType.START, NodeType.END_SUCCESS, NodeType.END_REJECT):
                    w, h = 156.0, 52.0
                elif nt == NodeType.PARALLEL:
                    w, h = 148.0, 56.0
                else:
                    w, h = NODE_W, NODE_H
                node_box[nid] = (cx, cy, w, h)

        parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(total_w)} {_fmt(total_h)}" '
            f'width="{_fmt(total_w)}" height="{_fmt(total_h)}" role="img" '
            f'aria-label="{_xml_safe(graph.title, 120)}">',
            f"<title>{_xml_safe(graph.title, 120)}</title>",
            self._svg_defs(),
            f'<rect x="0" y="0" width="{_fmt(total_w)}" height="{_fmt(total_h)}" fill="#FFFFFF"/>',
            # Executive Process Title Header
            f'<text x="{_fmt(PAD_X)}" y="31" font-family="Inter, Segoe UI, Arial, sans-serif" '
            f'font-size="16" font-weight="700" fill="#0F172A">{_xml_safe(graph.title, 92)}</text>',
            f'<text x="{_fmt(total_w - PAD_X)}" y="31" text-anchor="end" font-family="Inter, Segoe UI, Arial, sans-serif" '
            f'font-size="11" font-weight="600" fill="#64748B">BPMN 2.0 Swimlane · Left → Right</text>',
        ]

        # 1. Swimlane Bands (Full Width, Stacked Top-to-Bottom)
        board_x = PAD_X
        board_w = total_w - 2.0 * PAD_X
        parts.append('<g class="alvea-lanes">')
        for idx, ln in enumerate(ordered_lanes):
            y0, y1 = lane_bounds[ln.id]
            lh = y1 - y0
            band_bg = "#FFFFFF" if idx % 2 == 0 else "#F8F7F3"
            accent = lane_accent[ln.id]
            # Band body
            parts.append(
                f'<rect x="{_fmt(board_x)}" y="{_fmt(y0)}" width="{_fmt(board_w)}" height="{_fmt(lh)}" '
                f'fill="{band_bg}" stroke="#CBD5E1" stroke-width="1"/>'
            )
            # Left lane header block
            parts.append(
                f'<rect x="{_fmt(board_x)}" y="{_fmt(y0)}" width="{_fmt(HEADER_W)}" height="{_fmt(lh)}" '
                f'fill="#F1F5F9" stroke="#CBD5E1" stroke-width="1"/>'
            )
            # 4px color accent rail
            parts.append(
                f'<rect x="{_fmt(board_x)}" y="{_fmt(y0)}" width="5" height="{_fmt(lh)}" fill="{accent}"/>'
            )
            # Lane title + role kind subtitle
            lane_lines = _wrap_lines(ln.name, max_chars=17, max_lines=2)
            text_x = board_x + 16.0
            mid_y = y0 + lh * 0.5 - (len(lane_lines) - 1) * 7.5 - 4.0
            tspans = "".join(
                f'<tspan x="{_fmt(text_x)}" dy="{"0" if i == 0 else "15"}">{_xml_safe(line, 40)}</tspan>'
                for i, line in enumerate(lane_lines)
            )
            parts.append(
                f'<text x="{_fmt(text_x)}" y="{_fmt(mid_y)}" font-family="Inter, Segoe UI, Arial, sans-serif" '
                f'font-size="12.5" font-weight="700" fill="#0F172A">{tspans}</text>'
            )
            kind_y = mid_y + len(lane_lines) * 15.0 + 3.0
            parts.append(
                f'<text x="{_fmt(text_x)}" y="{_fmt(kind_y)}" font-family="Inter, Segoe UI, Arial, sans-serif" '
                f'font-size="10" font-weight="600" fill="#64748B">{_xml_safe(ln.kind.value.upper(), 20)}</text>'
            )
        # Outer frame
        board_h = cur_y - PAD_TOP
        parts.append(
            f'<rect x="{_fmt(board_x)}" y="{_fmt(PAD_TOP)}" width="{_fmt(board_w)}" height="{_fmt(board_h)}" '
            f'rx="8" fill="none" stroke="#94A3B8" stroke-width="1.2"/>'
        )
        parts.append("</g>")

        # 2. Edges (Orthogonal Routing + Pill Labels)
        parts.append('<g class="alvea-edges">')
        gutter_usage: dict[int, int] = {}
        loop_count = 0
        placed_labels: list[tuple[float, float]] = []

        # Precompute fan-in / fan-out indices for clean port spacing
        in_edges_map: dict[str, list[ProcessEdge]] = {n.id: [] for n in graph.nodes}
        out_edges_map: dict[str, list[ProcessEdge]] = {n.id: [] for n in graph.nodes}
        for e in graph.edges:
            if e.source in node_box and e.target in node_box:
                out_edges_map[e.source].append(e)
                in_edges_map[e.target].append(e)

        for e in graph.edges:
            if e.source not in node_box or e.target not in node_box:
                continue
            src_box = node_box[e.source]
            tgt_box = node_box[e.target]
            c1 = col.get(e.source, 0)
            c2 = col.get(e.target, 0)
            is_loop = e.is_loop or (e.source, e.target) in back_edges or c2 <= c1
            is_crit = (e.source, e.target) in critical_edges

            # Determine source exit point & target entry point
            sx, sy = self._lr_exit_port(e, src_box, tgt_box, out_edges_map[e.source], node_by_id[e.source].node_type)
            tx, ty = self._lr_entry_port(e, src_box, tgt_box, in_edges_map[e.target], is_loop=is_loop)

            if is_loop:
                loop_count += 1
                lane_y1 = max(lane_bounds[node_by_id[e.source].lane_id][1], lane_bounds[node_by_id[e.target].lane_id][1])
                y_corr = min(total_h - 16.0, lane_y1 - 12.0 + (loop_count % 3) * 10.0)
                x_exit = sx + 18.0
                x_entry = tx - 22.0
                pts = [(sx, sy), (x_exit, sy), (x_exit, y_corr), (x_entry, y_corr), (x_entry, ty), (tx, ty)]
                lbl_x = (x_exit + x_entry) * 0.5
                lbl_y = y_corr - 9.0
            elif c2 == c1 + 1 and abs(sy - ty) <= 4.0:
                pts = [(sx, sy), (tx, ty)]
                lbl_x = (sx + tx) * 0.5
                lbl_y = sy - 11.0
            else:
                # Forward orthogonal routing through inter-column gutter
                slot = gutter_usage.get(c1, 0)
                gutter_usage[c1] = slot + 1
                gutter_base = PAD_X + HEADER_W + (c1 + 1) * COL_W - 36.0
                x_gut = gutter_base + ((slot % 5) - 2) * 8.0
                if x_gut <= sx + 10.0:
                    x_gut = sx + 16.0

                same_lane = node_by_id[e.source].lane_id == node_by_id[e.target].lane_id
                has_obstacle_same_row = same_lane and c2 - c1 > 1 and any(
                    (node_by_id[e.source].lane_id, mid_c) in cells for mid_c in range(c1 + 1, c2)
                )

                if has_obstacle_same_row:
                    # Route cleanly along top corridor of the lane so arrows NEVER cross intermediate boxes
                    lane_y0 = lane_bounds[node_by_id[e.source].lane_id][0]
                    y_corr = lane_y0 + 13.0 + (slot % 3) * 7.0
                    x_pre_tgt = tx - 18.0
                    pts = [(sx, sy), (x_gut, sy), (x_gut, y_corr), (x_pre_tgt, y_corr), (x_pre_tgt, ty), (tx, ty)]
                    lbl_x = (x_gut + x_pre_tgt) * 0.5
                    lbl_y = y_corr - 8.0
                else:
                    # Standard clean 3-segment Z-route using gutter closest to target if multi-column
                    if c2 - c1 > 1:
                        t_slot = gutter_usage.get(c2 - 1, 0)
                        gutter_usage[c2 - 1] = t_slot + 1
                        x_gut = PAD_X + HEADER_W + c2 * COL_W - 36.0 + ((t_slot % 5) - 2) * 8.0
                        if x_gut >= tx - 10.0:
                            x_gut = tx - 16.0
                        if x_gut <= sx + 10.0:
                            x_gut = (sx + tx) * 0.5
                    pts = [(sx, sy), (x_gut, sy), (x_gut, ty), (tx, ty)]
                    if abs(sy - ty) > 20.0:
                        if (x_gut - sx) > 54:
                            lbl_x = (sx + x_gut) * 0.5 + 8.0
                            lbl_y = (sy + 12.0) if ty > sy else (sy - 12.0)
                        else:
                            lbl_x = x_gut + 4.0
                            lbl_y = (sy + ty) * 0.5
                    else:
                        lbl_x = (sx + tx) * 0.5
                        lbl_y = (sy + ty) * 0.5 - 11.0

            d_attr = _rounded_ortho_path(pts, radius=8.0)
            if is_crit:
                stroke, sw, dash, marker, opacity = "#4338CA", "2.6", "", "url(#arrow-critical)", "1"
            elif is_loop:
                stroke, sw, dash, marker, opacity = "#DC2626", "1.8", ' stroke-dasharray="6 4"', "url(#arrow-loop)", "0.95"
            elif e.is_parallel:
                stroke, sw, dash, marker, opacity = "#0D9488", "1.8", "", "url(#arrow-parallel)", "0.95"
            else:
                opacity = "0.52" if highlight_critical else "0.92"
                stroke, sw, dash, marker = "#64748B", "1.7", "", "url(#arrow-std)"

            parts.append(
                f'<path d="{d_attr}" fill="none" stroke="{stroke}" stroke-width="{sw}"{dash} '
                f'opacity="{opacity}" stroke-linejoin="round" stroke-linecap="round" marker-end="{marker}"/>'
            )

            if e.label:
                # Collision avoidance for nearby pill labels
                for px, py in placed_labels:
                    if abs(lbl_x - px) < 76.0 and abs(lbl_y - py) < 20.0:
                        lbl_y += 20.0
                placed_labels.append((lbl_x, lbl_y))
                parts.append(self._render_edge_pill(lbl_x, lbl_y, e.label, is_loop=is_loop))

        parts.append("</g>")

        # 3. BPMN Nodes
        parts.append('<g class="alvea-nodes">')
        for n in graph.nodes:
            if n.id not in node_box:
                continue
            cx, cy, w, h = node_box[n.id]
            is_crit = n.id in critical_nodes
            dimmed = bool(highlight_critical and not is_crit)
            parts.append(
                self._render_node(
                    n,
                    cx=cx,
                    cy=cy,
                    w=w,
                    h=h,
                    accent=lane_accent.get(n.lane_id, "#1E3A5F"),
                    is_critical=is_crit,
                    dimmed=dimmed,
                )
            )
        parts.append("</g>")
        parts.append("</svg>")
        return "\n".join(parts)

    @staticmethod
    def _lr_exit_port(
        edge: ProcessEdge,
        src_box: tuple[float, float, float, float],
        tgt_box: tuple[float, float, float, float],
        out_edges: list[ProcessEdge],
        node_type: NodeType,
    ) -> tuple[float, float]:
        cx, cy, w, h = src_box
        _, tcy, _, _ = tgt_box
        if node_type == NodeType.DECISION and len(out_edges) >= 2:
            if tcy < cy - 28.0:
                return (cx, cy - h * 0.5)
            if tcy > cy + 28.0:
                return (cx, cy + h * 0.5)
            return (cx + w * 0.5, cy)
        idx = out_edges.index(edge) if edge in out_edges else 0
        count = max(1, len(out_edges))
        offset = ((idx - (count - 1) * 0.5) * 14.0) if count > 1 else 0.0
        return (cx + w * 0.5, cy + max(-h * 0.3, min(h * 0.3, offset)))

    @staticmethod
    def _lr_entry_port(
        edge: ProcessEdge,
        src_box: tuple[float, float, float, float],
        tgt_box: tuple[float, float, float, float],
        in_edges: list[ProcessEdge],
        *,
        is_loop: bool,
    ) -> tuple[float, float]:
        cx, cy, w, h = tgt_box
        if is_loop:
            return (cx - w * 0.5, cy + min(h * 0.25, 14.0))
        idx = in_edges.index(edge) if edge in in_edges else 0
        count = max(1, len(in_edges))
        offset = ((idx - (count - 1) * 0.5) * 12.0) if count > 1 else 0.0
        return (cx - w * 0.5, cy + max(-h * 0.3, min(h * 0.3, offset)))

    # ─── Vertical Swimlanes (TD: Columns = Lanes, Rows = Top -> Bottom) ────────

    def _render_vertical_td(
        self,
        graph: ProcessGraph,
        *,
        analytics: GraphAnalytics | None,
        highlight_critical: bool,
        align_ends_right: bool,
    ) -> str:
        node_by_id = {n.id: n for n in graph.nodes}
        G_dag, row_rank, back_edges = self._compute_dag_and_layers(graph, align_ends_right=align_ends_right)

        critical_nodes = set(analytics.critical_path) if (analytics and highlight_critical) else set()
        critical_edges: set[tuple[str, str]] = set()
        if analytics and highlight_critical and len(analytics.critical_path) >= 2:
            for a, b in zip(analytics.critical_path, analytics.critical_path[1:]):
                critical_edges.add((a, b))

        ordered_lanes = sorted(graph.lanes, key=lambda ln: ln.order)
        lane_accent = {
            ln.id: LANE_ACCENT_PALETTE[idx % len(LANE_ACCENT_PALETTE)]
            for idx, ln in enumerate(ordered_lanes)
        }
        num_rows = max(row_rank.values(), default=0) + 1

        cells: dict[tuple[str, int], list[str]] = {}
        for n in graph.nodes:
            cells.setdefault((n.lane_id, row_rank.get(n.id, 0)), []).append(n.id)

        PAD_X = 24.0
        PAD_TOP = 54.0
        PAD_BOTTOM = 36.0
        HEADER_H = 54.0
        ROW_H = 126.0
        SUBCOL_W = 196.0
        LANE_PAD_X = 22.0

        lane_bounds_x: dict[str, tuple[float, float]] = {}
        cur_x = PAD_X
        for ln in ordered_lanes:
            max_stack = max((len(cells.get((ln.id, r), [])) for r in range(num_rows)), default=1)
            lw = max(210.0, max(1, max_stack) * SUBCOL_W + 2.0 * LANE_PAD_X)
            lane_bounds_x[ln.id] = (cur_x, cur_x + lw)
            cur_x += lw

        total_w = min(float(MAX_SVG_WIDTH), max(720.0, cur_x + PAD_X))
        total_h = min(float(MAX_SVG_HEIGHT), PAD_TOP + HEADER_H + num_rows * ROW_H + PAD_BOTTOM)

        node_box: dict[str, tuple[float, float, float, float]] = {}
        for (lid, r), nids in cells.items():
            x0, x1 = lane_bounds_x[lid]
            lw = x1 - x0
            cy = PAD_TOP + HEADER_H + r * ROW_H + ROW_H * 0.5
            stack_w = len(nids) * SUBCOL_W
            start_cx = x0 + (lw - stack_w) * 0.5 + SUBCOL_W * 0.5
            for k, nid in enumerate(nids):
                cx = start_cx + k * SUBCOL_W
                nt = node_by_id[nid].node_type
                if nt == NodeType.DECISION:
                    w, h = 152.0, 74.0
                elif nt in (NodeType.START, NodeType.END_SUCCESS, NodeType.END_REJECT):
                    w, h = 156.0, 52.0
                elif nt == NodeType.PARALLEL:
                    w, h = 148.0, 56.0
                else:
                    w, h = 166.0, 62.0
                node_box[nid] = (cx, cy, w, h)

        parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_fmt(total_w)} {_fmt(total_h)}" '
            f'width="{_fmt(total_w)}" height="{_fmt(total_h)}" role="img" '
            f'aria-label="{_xml_safe(graph.title, 120)}">',
            f"<title>{_xml_safe(graph.title, 120)}</title>",
            self._svg_defs(),
            f'<rect x="0" y="0" width="{_fmt(total_w)}" height="{_fmt(total_h)}" fill="#FFFFFF"/>',
            f'<text x="{_fmt(PAD_X)}" y="31" font-family="Inter, Segoe UI, Arial, sans-serif" '
            f'font-size="16" font-weight="700" fill="#0F172A">{_xml_safe(graph.title, 92)}</text>',
            f'<text x="{_fmt(total_w - PAD_X)}" y="31" text-anchor="end" font-family="Inter, Segoe UI, Arial, sans-serif" '
            f'font-size="11" font-weight="600" fill="#64748B">BPMN 2.0 Swimlane · Top → Down</text>',
        ]

        board_h = total_h - PAD_TOP - PAD_BOTTOM
        parts.append('<g class="alvea-lanes">')
        for idx, ln in enumerate(ordered_lanes):
            x0, x1 = lane_bounds_x[ln.id]
            lw = x1 - x0
            bg = "#FFFFFF" if idx % 2 == 0 else "#F8F7F3"
            accent = lane_accent[ln.id]
            parts.append(
                f'<rect x="{_fmt(x0)}" y="{_fmt(PAD_TOP)}" width="{_fmt(lw)}" height="{_fmt(board_h)}" '
                f'fill="{bg}" stroke="#CBD5E1" stroke-width="1"/>'
            )
            parts.append(
                f'<rect x="{_fmt(x0)}" y="{_fmt(PAD_TOP)}" width="{_fmt(lw)}" height="{_fmt(HEADER_H)}" '
                f'fill="#F1F5F9" stroke="#CBD5E1" stroke-width="1"/>'
            )
            parts.append(
                f'<rect x="{_fmt(x0)}" y="{_fmt(PAD_TOP)}" width="{_fmt(lw)}" height="4" fill="{accent}"/>'
            )
            parts.append(
                f'<text x="{_fmt(x0 + lw * 0.5)}" y="{_fmt(PAD_TOP + 26)}" text-anchor="middle" '
                f'font-family="Inter, Segoe UI, Arial, sans-serif" font-size="12.5" font-weight="700" fill="#0F172A">'
                f'{_xml_safe(ln.name, 26)}</text>'
            )
            parts.append(
                f'<text x="{_fmt(x0 + lw * 0.5)}" y="{_fmt(PAD_TOP + 42)}" text-anchor="middle" '
                f'font-family="Inter, Segoe UI, Arial, sans-serif" font-size="9.5" font-weight="600" fill="#64748B">'
                f'{_xml_safe(ln.kind.value.upper(), 20)}</text>'
            )
        parts.append("</g>")

        parts.append('<g class="alvea-edges">')
        for idx, e in enumerate(graph.edges):
            if e.source not in node_box or e.target not in node_box:
                continue
            sx, sy, sw_n, sh_n = node_box[e.source]
            tx, ty, tw_n, th_n = node_box[e.target]
            r1, r2 = row_rank.get(e.source, 0), row_rank.get(e.target, 0)
            is_loop = e.is_loop or (e.source, e.target) in back_edges or r2 <= r1
            is_crit = (e.source, e.target) in critical_edges

            if is_loop:
                x_corr = min(total_w - 16.0, max(sx + sw_n * 0.5, tx + tw_n * 0.5) + 22.0 + (idx % 3) * 8.0)
                pts = [(sx + sw_n * 0.5, sy), (x_corr, sy), (x_corr, ty), (tx + tw_n * 0.5, ty)]
                lx, ly = x_corr - 8.0, (sy + ty) * 0.5
            else:
                p_start = (sx, sy + sh_n * 0.5)
                p_end = (tx, ty - th_n * 0.5)
                mid_y = (p_start[1] + p_end[1]) * 0.5 + ((idx % 3) - 1) * 6.0
                pts = [p_start, (sx, mid_y), (tx, mid_y), p_end]
                lx, ly = (sx + tx) * 0.5, mid_y - 9.0

            d_attr = _rounded_ortho_path(pts, radius=8.0)
            if is_crit:
                stroke, sw, dash, marker, opacity = "#4338CA", "2.6", "", "url(#arrow-critical)", "1"
            elif is_loop:
                stroke, sw, dash, marker, opacity = "#DC2626", "1.8", ' stroke-dasharray="6 4"', "url(#arrow-loop)", "0.95"
            else:
                opacity = "0.52" if highlight_critical else "0.92"
                stroke, sw, dash, marker = "#64748B", "1.7", "", "url(#arrow-std)"

            parts.append(
                f'<path d="{d_attr}" fill="none" stroke="{stroke}" stroke-width="{sw}"{dash} '
                f'opacity="{opacity}" stroke-linejoin="round" stroke-linecap="round" marker-end="{marker}"/>'
            )
            if e.label:
                parts.append(self._render_edge_pill(lx, ly, e.label, is_loop=is_loop))
        parts.append("</g>")

        parts.append('<g class="alvea-nodes">')
        for n in graph.nodes:
            if n.id not in node_box:
                continue
            cx, cy, w, h = node_box[n.id]
            is_crit = n.id in critical_nodes
            parts.append(
                self._render_node(
                    n,
                    cx=cx,
                    cy=cy,
                    w=w,
                    h=h,
                    accent=lane_accent.get(n.lane_id, "#1E3A5F"),
                    is_critical=is_crit,
                    dimmed=bool(highlight_critical and not is_crit),
                )
            )
        parts.append("</g>")
        parts.append("</svg>")
        return "\n".join(parts)

    # ─── Vector Primitives & Defs ──────────────────────────────────────────────

    @staticmethod
    def _svg_defs() -> str:
        return """<defs>
  <marker id="arrow-std" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
    <path d="M 0 1 L 10 5 L 0 9 z" fill="#64748B"/>
  </marker>
  <marker id="arrow-critical" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
    <path d="M 0 1 L 10 5 L 0 9 z" fill="#4338CA"/>
  </marker>
  <marker id="arrow-loop" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
    <path d="M 0 1 L 10 5 L 0 9 z" fill="#DC2626"/>
  </marker>
  <marker id="arrow-parallel" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6.5" markerHeight="6.5" orient="auto-start-reverse">
    <path d="M 0 1 L 10 5 L 0 9 z" fill="#0D9488"/>
  </marker>
</defs>"""

    @staticmethod
    def _render_edge_pill(x: float, y: float, label: str, *, is_loop: bool) -> str:
        text = sanitize_label_text(label, max_len=24)
        fill, stroke, fg = _edge_pill_style(text, is_loop)
        pill_w = max(36.0, min(148.0, len(text) * 6.4 + 14.0))
        pill_h = 18.0
        px = x - pill_w * 0.5
        py = y - pill_h * 0.5
        return (
            f'<g class="alvea-edge-label">'
            f'<rect x="{_fmt(px)}" y="{_fmt(py)}" width="{_fmt(pill_w)}" height="{_fmt(pill_h)}" '
            f'rx="9" fill="{fill}" stroke="{stroke}" stroke-width="1"/>'
            f'<text x="{_fmt(x)}" y="{_fmt(y + 3.5)}" text-anchor="middle" '
            f'font-family="Inter, Segoe UI, Arial, sans-serif" font-size="10" font-weight="600" fill="{fg}">'
            f'{_xml_safe(text, 24)}</text>'
            f"</g>"
        )

    @staticmethod
    def _render_node(
        node: ProcessNode,
        *,
        cx: float,
        cy: float,
        w: float,
        h: float,
        accent: str,
        is_critical: bool,
        dimmed: bool,
    ) -> str:
        x = cx - w * 0.5
        y = cy - h * 0.5
        nt = node.node_type
        opacity_attr = ' opacity="0.52"' if dimmed else ""
        stroke_crit = "#4338CA" if is_critical else None
        sw_crit = "2.8" if is_critical else None

        elems: list[str] = [
            f'<g class="alvea-node" data-node-id="{_xml_safe(node.id, 40)}" '
            f'data-lane-id="{_xml_safe(node.lane_id, 40)}" data-node-type="{nt.value}"{opacity_attr}>'
        ]

        text_max_chars = 20
        text_y_shift = 0.0
        text_color = "#0F172A"

        if nt == NodeType.START:
            st = stroke_crit or "#16A34A"
            sw = sw_crit or "2.2"
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'rx="{_fmt(h * 0.5)}" fill="#DCFCE7" stroke="{st}" stroke-width="{sw}"/>'
            )
            # Play icon on left
            px0, py0 = x + 16.0, cy
            elems.append(
                f'<polygon points="{_fmt(px0)},{_fmt(py0 - 6)} {_fmt(px0 + 9)},{_fmt(py0)} {_fmt(px0)},{_fmt(py0 + 6)}" fill="#15803D"/>'
            )
            text_color = "#14532D"
            text_max_chars = 18

        elif nt in (NodeType.END_SUCCESS, NodeType.END_REJECT):
            is_ok = nt == NodeType.END_SUCCESS
            fill = "#DCFCE7" if is_ok else "#FEE2E2"
            st = stroke_crit or ("#15803D" if is_ok else "#B91C1C")
            sw = sw_crit or "3.0"
            text_color = "#14532D" if is_ok else "#7F1D1D"
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'rx="{_fmt(h * 0.5)}" fill="{fill}" stroke="{st}" stroke-width="{sw}"/>'
            )
            text_max_chars = 18

        elif nt == NodeType.DECISION:
            st = stroke_crit or "#D97706"
            sw = sw_crit or "2.0"
            pts = f"{_fmt(cx)},{_fmt(y)} {_fmt(x + w)},{_fmt(cy)} {_fmt(cx)},{_fmt(y + h)} {_fmt(x)},{_fmt(cy)}"
            elems.append(f'<polygon points="{pts}" fill="#FEF9C3" stroke="{st}" stroke-width="{sw}"/>')
            text_color = "#78350F"
            text_max_chars = 16

        elif nt == NodeType.PARALLEL:
            st = stroke_crit or "#0D9488"
            sw = sw_crit or "2.0"
            dx = 16.0
            pts = (
                f"{_fmt(x + dx)},{_fmt(y)} {_fmt(x + w - dx)},{_fmt(y)} {_fmt(x + w)},{_fmt(cy)} "
                f"{_fmt(x + w - dx)},{_fmt(y + h)} {_fmt(x + dx)},{_fmt(y + h)} {_fmt(x)},{_fmt(cy)}"
            )
            elems.append(f'<polygon points="{pts}" fill="#CCFBF1" stroke="{st}" stroke-width="{sw}"/>')
            text_color = "#134E4A"
            text_max_chars = 16

        elif nt == NodeType.SYSTEM:
            st = stroke_crit or "#0284C7"
            sw = sw_crit or "1.8"
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'rx="8" fill="#E0F2FE" stroke="{st}" stroke-width="{sw}"/>'
            )
            # Subtle automated top bar
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="6" rx="3" fill="{st}"/>'
            )
            elems.append(
                f'<text x="{_fmt(x + 9)}" y="{_fmt(y + 16)}" font-family="Inter, Segoe UI, Arial, sans-serif" '
                f'font-size="8.5" font-weight="700" fill="#0369A1">AUTO</text>'
            )
            text_color = "#0C4A6E"
            text_y_shift = 4.0

        elif nt == NodeType.SUBPROCESS:
            st = stroke_crit or "#7C3AED"
            sw = sw_crit or "1.8"
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'rx="8" fill="#EDE9FE" stroke="{st}" stroke-width="{sw}"/>'
            )
            elems.append(f'<line x1="{_fmt(x + 10)}" y1="{_fmt(y)}" x2="{_fmt(x + 10)}" y2="{_fmt(y + h)}" stroke="{st}" stroke-width="1.2"/>')
            elems.append(f'<line x1="{_fmt(x + w - 10)}" y1="{_fmt(y)}" x2="{_fmt(x + w - 10)}" y2="{_fmt(y + h)}" stroke="{st}" stroke-width="1.2"/>')
            text_color = "#4C1D95"
            text_max_chars = 17

        elif nt == NodeType.WAIT:
            st = stroke_crit or "#EA580C"
            sw = sw_crit or "1.8"
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'rx="8" fill="#FFF7ED" stroke="{st}" stroke-width="{sw}"/>'
            )
            # Clock icon top-left
            elems.append(f'<circle cx="{_fmt(x + 13)}" cy="{_fmt(y + 13)}" r="5" fill="none" stroke="#C2410C" stroke-width="1.3"/>')
            elems.append(f'<path d="M {_fmt(x + 13)} {_fmt(y + 10)} L {_fmt(x + 13)} {_fmt(y + 13)} L {_fmt(x + 15.5)} {_fmt(y + 14)}" fill="none" stroke="#C2410C" stroke-width="1.3"/>')
            text_color = "#7C2D12"
            text_y_shift = 3.0

        else:  # TASK
            st = stroke_crit or "#94A3B8"
            sw = sw_crit or "1.5"
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y)}" width="{_fmt(w)}" height="{_fmt(h)}" '
                f'rx="8" fill="#FFFFFF" stroke="{st}" stroke-width="{sw}"/>'
            )
            elems.append(
                f'<rect x="{_fmt(x)}" y="{_fmt(y + 6)}" width="4" height="{_fmt(h - 12)}" rx="2" fill="{accent}"/>'
            )

        # Multi-line wrapped label (<text><tspan>)
        lines = _wrap_lines(node.label, max_chars=text_max_chars, max_lines=3 if nt != NodeType.START else 2)
        line_h = 13.5
        text_start_y = cy - (len(lines) - 1) * (line_h * 0.5) + 4.0 + text_y_shift
        text_cx = cx + (6.0 if nt == NodeType.START else 0.0)
        tspans = "".join(
            f'<tspan x="{_fmt(text_cx)}" dy="{"0" if i == 0 else _fmt(line_h)}">{_xml_safe(line, 44)}</tspan>'
            for i, line in enumerate(lines)
        )
        elems.append(
            f'<text x="{_fmt(text_cx)}" y="{_fmt(text_start_y)}" text-anchor="middle" '
            f'font-family="Inter, Segoe UI, Arial, sans-serif" font-size="11.2" font-weight="600" fill="{text_color}">'
            f"{tspans}</text>"
        )

        # Optional SLA / duration micro-badge bottom-right
        sla_txt = _format_sla_badge(node.estimated_duration_min)
        if sla_txt and nt not in (NodeType.START, NodeType.END_SUCCESS, NodeType.END_REJECT, NodeType.DECISION):
            bw = max(28.0, len(sla_txt) * 6.0 + 10.0)
            bx = x + w - bw - 5.0
            by = y + h - 16.0
            elems.append(
                f'<rect x="{_fmt(bx)}" y="{_fmt(by)}" width="{_fmt(bw)}" height="13" rx="6" fill="#F1F5F9" stroke="#CBD5E1" stroke-width="0.8"/>'
            )
            elems.append(
                f'<text x="{_fmt(bx + bw * 0.5)}" y="{_fmt(by + 9.5)}" text-anchor="middle" '
                f'font-family="Inter, Segoe UI, Arial, sans-serif" font-size="8.5" font-weight="700" fill="#475569">'
                f'{_xml_safe(sla_txt, 12)}</text>'
            )

        elems.append("</g>")
        return "\n".join(elems)
