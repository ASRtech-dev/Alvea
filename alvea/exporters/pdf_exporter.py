"""Executive Multipage PDF Exporter (ReportLab 4.4 + Pillow 12.1, English Default)."""

from __future__ import annotations

import base64
import io
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from PIL import Image as PILImage
from reportlab.graphics.shapes import Drawing, Line, Rect, String
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image as RLImage,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from alvea.models import ExecutiveReport, GraphAnalytics, ProcessGraph

BRAND_NAVY = colors.HexColor("#1E3A5F")
BRAND_SLATE = colors.HexColor("#475569")
SURFACE_LIGHT = colors.HexColor("#F6F5F0")
BORDER_GRAY = colors.HexColor("#CBD5E1")


def _to_winansi_safe(text: str) -> str:
    """Normalize non-WinAnsi Unicode glyphs for ReportLab Type-1 Helvetica/Courier."""
    return (
        str(text or "")
        .replace("→", "->")
        .replace("←", "<-")
        .replace("≥", ">=")
        .replace("≤", "<=")
        .replace("…", "...")
        .replace("—", "-")
        .replace("–", "-")
        .replace("•", "-")
    )


def _safe_p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(xml_escape(_to_winansi_safe(text)), style)


def _build_embedded_diagram(diagram_png_base64: str | None, max_w: float, max_h: float) -> RLImage | None:
    if not diagram_png_base64:
        return None
    raw = diagram_png_base64.strip()
    if "," in raw and raw.startswith("data:image/png;base64,"):
        raw = raw.split(",", 1)[1]
    try:
        img_bytes = base64.b64decode(raw, validate=True)
        with PILImage.open(io.BytesIO(img_bytes)) as pil_img:
            if pil_img.format != "PNG":
                return None
            # Check dimensions BEFORE pixel decode (anti-decompression bomb)
            w, h = pil_img.size
            if w <= 0 or h <= 0 or w > 10_000 or h > 10_000 or (w * h) > 25_000_000:
                return None
            pil_img = pil_img.convert("RGB")
            ratio = min(max_w / w, max_h / h)
            draw_w = max(4 * cm, w * ratio)
            draw_h = max(2.5 * cm, h * ratio)
            buf = io.BytesIO()
            pil_img.save(buf, format="PNG", optimize=True)
            buf.seek(0)
            return RLImage(buf, width=draw_w, height=draw_h)
    except Exception:
        return None


def _build_vector_schematic(graph: ProcessGraph, width: float = 17.2 * cm) -> Drawing:
    """Generates a native ReportLab vector swimlane schematic when no PNG is attached."""
    lanes = graph.lanes[:6]
    lane_h = 34
    height = max(90, len(lanes) * lane_h + 24)
    drawing = Drawing(width, height)

    nodes_by_lane: dict[str, list] = {ln.id: [] for ln in lanes}
    for n in graph.nodes:
        if n.lane_id in nodes_by_lane:
            nodes_by_lane[n.lane_id].append(n)

    fill_map = {
        "start": colors.HexColor("#DCFCE7"),
        "end_success": colors.HexColor("#DCFCE7"),
        "end_reject": colors.HexColor("#FEE2E2"),
        "decision": colors.HexColor("#FEF9C3"),
        "system": colors.HexColor("#E0F2FE"),
        "subprocess": colors.HexColor("#EDE9FE"),
        "wait": colors.HexColor("#FFF7ED"),
        "parallel": colors.HexColor("#CCFBF1"),
        "task": colors.white,
    }

    for idx, lane in enumerate(lanes):
        y = height - (idx + 1) * lane_h - 10
        bg = colors.HexColor("#F8FAFC") if idx % 2 == 0 else colors.white
        drawing.add(Rect(0, y, width, lane_h - 3, fillColor=bg, strokeColor=BORDER_GRAY, strokeWidth=0.6))
        drawing.add(Rect(0, y, 105, lane_h - 3, fillColor=BRAND_NAVY, strokeColor=BRAND_NAVY, strokeWidth=0.6))
        lane_lbl = _to_winansi_safe((lane.name[:17] + "...") if len(lane.name) > 18 else lane.name)
        drawing.add(String(6, y + 11, lane_lbl, fontName="Helvetica-Bold", fontSize=7.5, fillColor=colors.white))

        ln_nodes = nodes_by_lane.get(lane.id, [])[:5]
        x = 116
        step_w = max(58, (width - 130) / max(1, len(ln_nodes)) - 8)
        for n_idx, node in enumerate(ln_nodes):
            fill = fill_map.get(node.node_type.value, colors.white)
            drawing.add(Rect(x, y + 5, min(step_w, 96), lane_h - 13, rx=4, ry=4, fillColor=fill, strokeColor=BRAND_SLATE, strokeWidth=0.6))
            nlbl = _to_winansi_safe((node.label[:15] + "...") if len(node.label) > 16 else node.label)
            drawing.add(String(x + 4, y + 12, nlbl, fontName="Helvetica", fontSize=6.5, fillColor=colors.HexColor("#0F172A")))
            if n_idx < len(ln_nodes) - 1:
                x2 = x + min(step_w, 96)
                drawing.add(Line(x2, y + 15, x2 + 8, y + 15, strokeColor=BRAND_SLATE, strokeWidth=0.7))
            x += min(step_w, 96) + 8

    return drawing


def export_executive_pdf(
    *,
    graph: ProcessGraph,
    analytics: GraphAnalytics,
    report: ExecutiveReport,
    mermaid_code: str,
    diagram_png_base64: str | None = None,
) -> bytes:
    """Builds the multipage ALVEA Executive Report PDF in memory."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=_to_winansi_safe(f"ALVEA - {report.title}"),
        author="ALVEA Process Architecture Studio",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AlveaTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15.5,
        textColor=colors.white,
        leading=20,
    )
    subtitle_style = ParagraphStyle(
        "AlveaSubtitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        textColor=colors.HexColor("#DCE7F5"),
        leading=11,
    )
    h2_style = ParagraphStyle(
        "AlveaH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        textColor=BRAND_NAVY,
        spaceBefore=12,
        spaceAfter=5,
    )
    body_style = ParagraphStyle(
        "AlveaBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9.2,
        textColor=colors.HexColor("#1E293B"),
        leading=13.5,
    )
    mono_style = ParagraphStyle(
        "AlveaMono",
        parent=styles["Code"],
        fontName="Courier",
        fontSize=7.2,
        leading=9.5,
        textColor=colors.HexColor("#0F172A"),
        backColor=SURFACE_LIGHT,
        borderPadding=6,
    )

    story: list = []
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # 1. Executive Banner
    banner_table = Table(
        [
            [
                _safe_p(f"ALVEA - {report.title}", title_style),
                _safe_p(f"Grade: {report.efficiency_grade}", title_style),
            ],
            [
                _safe_p(
                    f"Executive Process Architecture Report (BPA + NetworkX) | Orientation: graph {graph.direction.value}",
                    subtitle_style,
                ),
                _safe_p(timestamp, subtitle_style),
            ],
        ],
        colWidths=[13.8 * cm, 3.6 * cm],
    )
    banner_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), BRAND_NAVY),
                ("LEFTPADDING", (0, 0), (-1, -1), 12),
                ("RIGHTPADDING", (0, 0), (-1, -1), 12),
                ("TOPPADDING", (0, 0), (-1, 0), 10),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 10),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(banner_table)
    story.append(Spacer(1, 0.4 * cm))

    # 2. Executive Summary
    story.append(_safe_p("1. Executive Summary", h2_style))
    story.append(_safe_p(report.summary, body_style))
    story.append(Spacer(1, 0.3 * cm))

    # 3. NetworkX KPI Table
    kpi_data = [
        ["Swimlanes", "Nodes / Edges", "Complexity", "Automation", "Handoffs", "Loops"],
        [
            str(analytics.lane_count),
            f"{analytics.node_count} / {analytics.edge_count}",
            f"M={analytics.cyclomatic_complexity} ({analytics.complexity_level})",
            f"{round(analytics.automation_ratio * 100)}%",
            f"{analytics.handoff_count} ({round(analytics.handoff_ratio * 100)}%)",
            str(len(analytics.cycles)),
        ],
    ]
    kpi_table = Table(kpi_data, colWidths=[2.2 * cm, 2.9 * cm, 3.6 * cm, 3.0 * cm, 3.5 * cm, 2.2 * cm])
    kpi_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), SURFACE_LIGHT),
                ("TEXTCOLOR", (0, 0), (-1, 0), BRAND_SLATE),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 7.8),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 1), (-1, 1), 9.5),
                ("TEXTCOLOR", (0, 1), (-1, 1), BRAND_NAVY),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("BOX", (0, 0), (-1, -1), 0.75, BORDER_GRAY),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_GRAY),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(kpi_table)
    story.append(Spacer(1, 0.4 * cm))

    # 4. Swimlane Visual Diagram
    story.append(_safe_p("2. Swimlane Architecture Visual", h2_style))
    embedded_img = _build_embedded_diagram(diagram_png_base64, max_w=17.2 * cm, max_h=8.5 * cm)
    story.append(embedded_img if embedded_img is not None else _build_vector_schematic(graph, width=17.2 * cm))
    story.append(Spacer(1, 0.35 * cm))

    # 5. Lane Breakdown
    story.append(_safe_p("3. Workload Distribution by Swimlane", h2_style))
    lane_rows = [["Swimlane / Actor", "Kind", "Nodes", "Share", "Auto.", "Handoffs (In/Out)"]]
    for lm in analytics.lane_metrics:
        lane_rows.append([
            _to_winansi_safe(lm.lane_name),
            lm.kind.capitalize(),
            str(lm.node_count),
            f"{lm.workload_pct}%",
            str(lm.automated_count),
            f"{lm.handoffs_in} / {lm.handoffs_out}",
        ])
    lane_table = Table(lane_rows, colWidths=[5.8 * cm, 2.5 * cm, 1.8 * cm, 2.2 * cm, 1.8 * cm, 3.3 * cm])
    lane_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), BRAND_NAVY),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8.2),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SURFACE_LIGHT]),
                ("GRID", (0, 0), (-1, -1), 0.4, BORDER_GRAY),
                ("ALIGN", (2, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(lane_table)
    story.append(Spacer(1, 0.3 * cm))

    # 6. Cognitive Framework (Phases A, B, C)
    story.append(_safe_p("4. BPA Cognitive Decomposition (Phases A, B & C)", h2_style))
    actors_txt = ", ".join(f"{a['name']} ({a['nodes']})" for a in report.cognitive.phase_a_actors)
    story.append(_safe_p(f"Phase A (Actors / Swimlanes): {actors_txt}", body_style))
    story.append(_safe_p(f"Phase B (Gateways & Decisions): {' | '.join(report.cognitive.phase_b_decisions[:5])}", body_style))
    story.append(_safe_p(f"Phase C (Routes & Optimization): {report.cognitive.phase_c_routes}", body_style))
    story.append(Spacer(1, 0.25 * cm))

    # 7. NetworkX Structural Diagnostics
    story.append(_safe_p("5. NetworkX Structural Diagnostics", h2_style))
    cp_chain = " -> ".join(analytics.critical_path_labels) if analytics.critical_path_labels else "N/A"
    cp_unit = f"{analytics.estimated_cycle_time_min} min" if analytics.estimated_cycle_time_min is not None else f"{analytics.critical_path_weight} pts"
    story.append(_safe_p(f"Critical Path ({len(analytics.critical_path)} steps | {cp_unit}): {cp_chain}", body_style))
    story.append(Spacer(1, 0.15 * cm))
    for finding in report.bottleneck_findings:
        story.append(_safe_p(f"- Bottleneck: {finding}", body_style))
    for rework in report.rework_findings:
        story.append(_safe_p(f"- Rework / Loops: {rework}", body_style))
    for anom in report.anomalies[:4]:
        story.append(_safe_p(f"- Anomaly [{anom.severity.upper()}]: {anom.message}", body_style))

    # 8. Priority Recommendations
    story.append(_safe_p("6. Actionable Recommendations", h2_style))
    for rec in report.recommendations:
        story.append(_safe_p(f"[{rec.priority} | {rec.category}] {rec.title}: {rec.detail}", body_style))
        story.append(Spacer(1, 0.1 * cm))

    # 9. Technical Mermaid Appendix
    story.append(_safe_p("7. Technical Appendix: Mermaid.js Source", h2_style))
    story.append(Preformatted(_to_winansi_safe(mermaid_code[:3800]), mono_style, maxLineLength=102))

    doc.build(story)
    return buffer.getvalue()
