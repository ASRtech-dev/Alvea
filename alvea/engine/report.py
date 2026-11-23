"""Generador dinámico de Fases Cognitivas (A, B, C) y Reporte Ejecutivo BPA.

Produce estructuras Pydantic 100% libres de HTML crudo (prevención XSS) alimentadas
directamente por métricas reales de NetworkX y hallazgos opcionales del LLM.
"""

from __future__ import annotations

from alvea.models import (
    CognitiveAnalysis,
    ExecutiveReport,
    GraphAnalytics,
    NodeType,
    ProcessGraph,
    RecommendationItem,
)


class ReportBuilder:
    """Construye Fases Cognitivas y Reporte Ejecutivo real para cualquier proceso."""

    def build(self, graph: ProcessGraph, analytics: GraphAnalytics) -> ExecutiveReport:
        cognitive = self._build_cognitive(graph, analytics)
        bottleneck_findings = self._build_bottleneck_findings(analytics)
        rework_findings = self._build_rework_findings(analytics)
        recommendations = self._build_recommendations(graph, analytics)

        summary = self._build_summary(graph, analytics)

        kpis = {
            "lanes": analytics.lane_count,
            "nodes": analytics.node_count,
            "edges": analytics.edge_count,
            "decisions": analytics.decision_count,
            "cyclomatic_complexity": analytics.cyclomatic_complexity,
            "complexity_level": analytics.complexity_level,
            "automation_pct": round(analytics.automation_ratio * 100, 1),
            "handoffs": analytics.handoff_count,
            "handoff_pct": round(analytics.handoff_ratio * 100, 1),
            "cycles": len(analytics.cycles),
            "critical_path_steps": len(analytics.critical_path),
            "anomalies": len(analytics.anomalies),
        }

        return ExecutiveReport(
            title=graph.title,
            summary=summary,
            efficiency_grade=analytics.efficiency_grade,
            kpis=kpis,
            cognitive=cognitive,
            lane_breakdown=analytics.lane_metrics,
            bottleneck_findings=bottleneck_findings,
            rework_findings=rework_findings,
            anomalies=analytics.anomalies,
            recommendations=recommendations,
        )

    @staticmethod
    def _build_cognitive(graph: ProcessGraph, analytics: GraphAnalytics) -> CognitiveAnalysis:
        phase_a = [
            {
                "id": lm.lane_id,
                "name": lm.lane_name,
                "kind": lm.kind,
                "nodes": lm.node_count,
                "workload_pct": lm.workload_pct,
            }
            for lm in analytics.lane_metrics
        ]

        edges_by_src: dict[str, list[str]] = {}
        for edge in graph.edges:
            edges_by_src.setdefault(edge.source, []).append(edge.label or edge.target)

        phase_b: list[str] = []
        for node in graph.nodes:
            if node.node_type == NodeType.DECISION:
                branches = edges_by_src.get(node.id, [])
                branch_str = " / ".join(branches) if branches else "Sin ramas definidas"
                phase_b.append(f"{node.label} → [{branch_str}]")

        if not phase_b:
            phase_b.append("Flujo predominantemente lineal sin compuertas de decisión explícitas.")

        dir_desc = "horizontal (graph LR)" if graph.direction.value == "LR" else "vertical (graph TD)"
        rework_desc = (
            f"{len(analytics.cycles)} bucle(s) de retroalimentación identificados"
            if analytics.cycles
            else "sin ciclos de retrabajo detectados"
        )
        phase_c = (
            f"Layout {dir_desc} con ordenamiento topológico de {analytics.lane_count} carriles; "
            f"camino crítico de {len(analytics.critical_path)} pasos (peso {analytics.critical_path_weight}), "
            f"{analytics.handoff_count} traspasos inter-carril ({round(analytics.handoff_ratio * 100)}%) y {rework_desc}."
        )

        return CognitiveAnalysis(
            phase_a_actors=phase_a,
            phase_b_decisions=phase_b,
            phase_c_routes=phase_c,
        )

    @staticmethod
    def _build_summary(graph: ProcessGraph, analytics: GraphAnalytics) -> str:
        if graph.ai_summary:
            return graph.ai_summary
        auto_pct = round(analytics.automation_ratio * 100)
        ho_pct = round(analytics.handoff_ratio * 100)
        return (
            f"El proceso '{graph.title}' integra {analytics.lane_count} actores/carriles y "
            f"{analytics.node_count} nodos con complejidad ciclomática {analytics.complexity_level.lower()} "
            f"(M = {analytics.cyclomatic_complexity}). Presenta un índice de automatización del {auto_pct}%, "
            f"{analytics.handoff_count} traspasos entre áreas ({ho_pct}% de las transiciones) y un camino crítico "
            f"de {len(analytics.critical_path)} etapas, obteniendo calificación operativa {analytics.efficiency_grade}."
        )

    @staticmethod
    def _build_bottleneck_findings(analytics: GraphAnalytics) -> list[str]:
        if not analytics.bottlenecks:
            return ["No se detectaron nodos de congestión críticos en la topología actual."]
        findings: list[str] = []
        for bn in analytics.bottlenecks[:3]:
            mode = "tarea manual" if bn.is_manual else "paso automatizado"
            findings.append(
                f"{bn.label} ({bn.lane_name}): índice de riesgo {bn.risk_score:.2f}, "
                f"centralidad {bn.betweenness:.2f}, {bn.handoff_pressure} traspaso(s) incidentes ({mode})."
            )
        return findings

    @staticmethod
    def _build_rework_findings(analytics: GraphAnalytics) -> list[str]:
        if not analytics.cycles:
            return ["No se detectaron ciclos de retrabajo; el flujo es acíclico o de salida directa ante rechazo."]
        findings: list[str] = []
        for idx, cyc in enumerate(analytics.cycles[:3], start=1):
            chain = " → ".join(cyc.labels[:5])
            lanes = ", ".join(cyc.lanes_involved)
            findings.append(
                f"Bucle #{idx} ({len(cyc.nodes)} nodos en {lanes}): {chain} → retorno."
            )
        return findings

    @staticmethod
    def _build_recommendations(
        graph: ProcessGraph,
        analytics: GraphAnalytics,
    ) -> list[RecommendationItem]:
        recs: list[RecommendationItem] = []

        # 1. Incorporar recomendaciones del LLM si existen
        for idx, ai_rec in enumerate(graph.ai_recommendations[:3], start=1):
            recs.append(
                RecommendationItem(
                    priority="Alta" if idx == 1 else "Media",
                    category="Arquitectura IA",
                    title=f"Mejora sugerida #{idx}",
                    detail=ai_rec,
                )
            )

        # 2. Reglas deterministas basadas en KPIs NetworkX
        top_manual = next((b for b in analytics.bottlenecks if b.is_manual and b.risk_score >= 0.35), None)
        if top_manual:
            recs.append(
                RecommendationItem(
                    priority="Alta",
                    category="Automatización",
                    title=f"Mitigar cuello de botella en '{top_manual.label}'",
                    detail=(
                        f"El paso manual '{top_manual.label}' ({top_manual.lane_name}) concentra alta intermediación "
                        f"(riesgo {top_manual.risk_score:.2f}). Evaluar pre-validación automática, reglas de negocio o RPA."
                    ),
                    target_nodes=[top_manual.node_id],
                )
            )

        if analytics.handoff_ratio > 0.55:
            recs.append(
                RecommendationItem(
                    priority="Media",
                    category="Reducción de Handoffs",
                    title="Reducir fricción por traspasos entre áreas",
                    detail=(
                        f"El {round(analytics.handoff_ratio * 100)}% de las transiciones cruzan de carril. "
                        "Consolidar validaciones contiguas y establecer SLAs automáticos entre bandejas reducirá tiempos muertos."
                    ),
                )
            )

        if analytics.cycles:
            cyc = analytics.cycles[0]
            recs.append(
                RecommendationItem(
                    priority="Alta",
                    category="Eliminación de Retrabajo",
                    title="Aplicar validación en origen (Shift-Left) sobre bucle detectado",
                    detail=(
                        f"Existe un ciclo de corrección que involucra a {', '.join(cyc.lanes_involved)}. "
                        "Agregar validaciones obligatorias en el formulario inicial reduce las devoluciones."
                    ),
                    target_nodes=cyc.nodes[:4],
                )
            )

        if analytics.automation_ratio < 0.35:
            recs.append(
                RecommendationItem(
                    priority="Media",
                    category="Transformación Digital",
                    title="Incrementar cobertura de automatización",
                    detail=(
                        f"Solo el {round(analytics.automation_ratio * 100)}% de los pasos operativos están automatizados. "
                        "Priorizar integraciones vía API y notificaciones automáticas en el camino crítico."
                    ),
                    target_nodes=analytics.critical_path[:3],
                )
            )

        high_anomalies = [a for a in analytics.anomalies if a.severity == "high"]
        if high_anomalies:
            recs.append(
                RecommendationItem(
                    priority="Alta",
                    category="Integridad Estructural",
                    title=f"Resolver {len(high_anomalies)} anomalía(s) estructural(es)",
                    detail=high_anomalies[0].message,
                    target_nodes=[a.node_id for a in high_anomalies[:3]],
                )
            )

        if not recs:
            recs.append(
                RecommendationItem(
                    priority="Baja",
                    category="Gobernanza",
                    title="Instrumentar telemetría de tiempos de ciclo",
                    detail="La estructura del proceso es sólida. Se sugiere monitorear tiempos reales en los nodos del camino crítico.",
                    target_nodes=analytics.critical_path[:3],
                )
            )

        return recs[:6]
