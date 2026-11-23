"""Exportador de Reporte Ejecutivo en PDF multipágina (ReportLab 4.4 + Pillow 12.1)."""

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
ACCENT_INDIGO = colors.HexColor("#4338CA")
SEM_GREEN = colors.HexColor("#15803D")
SEM_AMBER = colors.HexColor("#B45309")
SEM_RED = colors.HexColor("#B91C1C")


def _to_winansi_safe(text: str) -> str:
    """Reemplaza glifos Unicode no soportados por Helvetica/Courier (WinAnsiEncoding)."""
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
            # Validar dimensiones ANTES de decodificar píxeles (anti Decompression Bomb)
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


def _build_vector_schematic(graph: ProcessGraph, width: float = 17.0 * cm) -> Drawing:
    """Genera un diagrama vectorial esquemático nativo de carriles cuando no se adjunta PNG."""
    lanes = graph.lanes[:6]
    lane_h = 34
    height = max(90, len(lanes) * lane_h + 24)
    drawing = Drawing(width, height)

    nodes_by_lane: dict[str, list] = {ln.id: [] for ln in lanes}
    for n in graph.nodes:
        if n.lane_id in nodes_by_lane:
            nodes_by_lane[n.lane_id].append(n)

    for idx, lane in enumerate(lanes):
        y = height - (idx + 1) * lane_h - 10
        bg = colors.HexColor("#F8FAFC") if idx % 2 == 0 else colors.white
        drawing.add(Rect(0, y, width, lane_h - 3, fillColor=bg, strokeColor=BORDER_GRAY, strokeWidth=0.6))
        drawing.add(Rect(0, y, 105, lane_h - 3, fillColor=BRAND_NAVY, strokeColor=BRAND_NAVY, strokeWidth=0.6))
        lane_lbl = (lane.name[:17] + "…") if len(lane.name) > 18 else lane.name
        drawing.add(String(6, y + 11, lane_lbl, fontName="Helvetica-Bold", fontSize=7.5, fillColor=colors.white))

        ln_nodes = nodes_by_lane.get(lane.id, [])[:5]
        x = 116
        step_w = max(58, (width - 130) / max(1, len(ln_nodes)) - 8)
        for n_idx, node in enumerate(ln_nodes):
            fill = colors.HexColor("#DCFCE7") if node.node_type.value == "start" else (
                colors.HexColor("#FEF9C3") if node.node_type.value == "decision" else (
                    colors.HexColor("#FEE2E2") if node.node_type.value == "end_reject" else colors.white
                )
            )
            drawing.add(Rect(x, y + 5, min(step_w, 96), lane_h - 13, rx=4, ry=4, fillColor=fill, strokeColor=BRAND_SLATE, strokeWidth=0.6))
            nlbl = (node.label[:15] + "…") if len(node.label) > 16 else node.label
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
    """Genera el Reporte Ejecutivo ALVEA en PDF listo para descarga."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=1.8 * cm,
        rightMargin=1.8 * cm,
        topMargin=1.8 * cm,
        bottomMargin=1.8 * cm,
        title=f"ALVEA — {report.title}",
        author="ALVEA Process Architecture Studio",
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AlveaTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
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

    # 1. Banner Ejecutivo
    banner_table = Table(
        [
            [
                _safe_p(f"ALVEA — {report.title}", title_style),
                _safe_p(f"Grado: {report.efficiency_grade}", title_style),
            ],
            [
                _safe_p(
                    f"Reporte Ejecutivo de Arquitectura de Procesos (BPA + NetworkX) · Orientación: graph {graph.direction.value}",
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

    # 2. Resumen Ejecutivo
    story.append(_safe_p("1. Resumen Ejecutivo", h2_style))
    story.append(_safe_p(report.summary, body_style))
    story.append(Spacer(1, 0.3 * cm))

    # 3. Tarjetas KPI NetworkX
    kpi_data = [
        ["Carriles", "Nodos / Aristas", "Complejidad", "Automatización", "Handoffs", "Bucles"],
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

    # 4. Visualización del Diagrama
    story.append(_safe_p("2. Arquitectura Visual Swimlane", h2_style))
    embedded_img = _build_embedded_diagram(diagram_png_base64, max_w=17.2 * cm, max_h=8.5 * cm)
    if embedded_img is not None:
        story.append(embedded_img)
    else:
        story.append(_build_vector_schematic(graph, width=17.2 * cm))
    story.append(Spacer(1, 0.35 * cm))

    # 5. Desglose por Carril
    story.append(_safe_p("3. Distribución de Carga por Carril (Swimlanes)", h2_style))
    lane_rows = [["Carril / Actor", "Tipo", "Nodos", "% Carga", "Auto.", "Handoffs (In/Out)"]]
    for lm in analytics.lane_metrics:
        lane_rows.append([
            lm.lane_name,
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

    # 6. Marco Cognitivo BPA (Fases A, B, C)
    story.append(_safe_p("4. Marco Cognitivo Aplicado (Fases A, B y C)", h2_style))
    actors_txt = ", ".join(f"{a['name']} ({a['nodes']})" for a in report.cognitive.phase_a_actors)
    story.append(_safe_p(f"Fase A (Actores/Carriles): {actors_txt}", body_style))
    story.append(_safe_p(f"Fase B (Decisiones): {' | '.join(report.cognitive.phase_b_decisions[:5])}", body_style))
    story.append(_safe_p(f"Fase C (Rutas): {report.cognitive.phase_c_routes}", body_style))
    story.append(Spacer(1, 0.25 * cm))

    # 7. Analítica NetworkX: Camino Crítico, Cuellos de Botella y Bucles
    story.append(_safe_p("5. Diagnóstico Estructural NetworkX", h2_style))
    cp_chain = " -> ".join(analytics.critical_path_labels) if analytics.critical_path_labels else "No calculable"
    story.append(_safe_p(f"Camino crítico ({len(analytics.critical_path)} pasos · peso {analytics.critical_path_weight}): {cp_chain}", body_style))
    story.append(Spacer(1, 0.15 * cm))
    for finding in report.bottleneck_findings:
        story.append(_safe_p(f"- Cuello de botella: {finding}", body_style))
    for rework in report.rework_findings:
        story.append(_safe_p(f"- Retrabajo / Bucles: {rework}", body_style))
    for anom in report.anomalies[:4]:
        story.append(_safe_p(f"- Anomalía [{anom.severity.upper()}]: {anom.message}", body_style))

    # 8. Plan de Recomendaciones
    story.append(_safe_p("6. Plan de Recomendaciones Prioritarias", h2_style))
    for rec in report.recommendations:
        story.append(
            _safe_p(
                f"[{rec.priority} · {rec.category}] {rec.title}: {rec.detail}",
                body_style,
            )
        )
        story.append(Spacer(1, 0.1 * cm))

    # 9. Apéndice Técnico Mermaid (WinAnsi-safe y con maxLineLength)
    story.append(_safe_p("7. Apéndice Técnico: Código Mermaid.js", h2_style))
    story.append(Preformatted(_to_winansi_safe(mermaid_code[:3800]), mono_style, maxLineLength=102))

    doc.build(story)
    return buffer.getvalue()
