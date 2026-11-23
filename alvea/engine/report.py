"""Dynamic Cognitive Framework (Phases A, B, C) and Executive Report Builder (English Default).

Produces 100% structured Pydantic JSON (zero raw HTML) directly backed by live NetworkX metrics.
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


def _format_duration(minutes: float) -> str:
    if minutes >= 480:
        days = minutes / 480.0
        return f"{days:.1f}d ({round(minutes)}m)"
    if minutes >= 60:
        hours = int(minutes // 60)
        rem = round(minutes % 60)
        return f"{hours}h {rem}m" if rem else f"{hours}h"
    return f"{round(minutes, 1)}m"


class ReportBuilder:
    """Builds Cognitive Phases and Executive Report dynamically for any ProcessGraph."""

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
            "parallel_gateways": analytics.parallel_count,
            "wait_states": analytics.wait_count,
            "system_steps": analytics.system_count,
            "cyclomatic_complexity": analytics.cyclomatic_complexity,
            "complexity_level": analytics.complexity_level,
            "automation_pct": round(analytics.automation_ratio * 100, 1),
            "handoffs": analytics.handoff_count,
            "handoff_pct": round(analytics.handoff_ratio * 100, 1),
            "cycles": len(analytics.cycles),
            "critical_path_steps": len(analytics.critical_path),
            "duration_unit": analytics.duration_unit,
            "estimated_cycle_time_min": analytics.estimated_cycle_time_min,
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
                branch_str = " / ".join(branches) if branches else "No branches defined"
                phase_b.append(f"Decision: {node.label} -> [{branch_str}]")
            elif node.node_type == NodeType.PARALLEL:
                phase_b.append(f"Parallel Gateway: {node.label}")

        if not phase_b:
            phase_b.append("Primarily linear control flow with no explicit branching gateways.")

        dir_desc = "horizontal (graph LR)" if graph.direction.value == "LR" else "vertical (graph TD)"
        rework_desc = (
            f"{len(analytics.cycles)} rework loop(s) detected"
            if analytics.cycles
            else "no rework cycles detected"
        )
        cp_dur = (
            _format_duration(analytics.estimated_cycle_time_min)
            if analytics.estimated_cycle_time_min is not None
            else f"{analytics.critical_path_weight} pts"
        )
        phase_c = (
            f"Topologically ordered {dir_desc} layout across {analytics.lane_count} swimlanes; "
            f"critical path spans {len(analytics.critical_path)} steps ({cp_dur}), "
            f"{analytics.handoff_count} cross-lane handoffs ({round(analytics.handoff_ratio * 100)}%), and {rework_desc}."
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
        cp_metric = (
            f"an estimated cycle time of {_format_duration(analytics.estimated_cycle_time_min)}"
            if analytics.estimated_cycle_time_min is not None
            else f"a critical path of {len(analytics.critical_path)} steps"
        )
        return (
            f"Workflow '{graph.title}' spans {analytics.lane_count} swimlanes and {analytics.node_count} nodes "
            f"with {analytics.complexity_level.lower()} cyclomatic complexity (M = {analytics.cyclomatic_complexity}). "
            f"It achieves {auto_pct}% automation coverage, {analytics.handoff_count} inter-lane handoffs ({ho_pct}%), "
            f"and {cp_metric}, earning an operational efficiency grade of {analytics.efficiency_grade}."
        )

    @staticmethod
    def _build_bottleneck_findings(analytics: GraphAnalytics) -> list[str]:
        if not analytics.bottlenecks:
            return ["No critical congestion nodes detected in the current topology."]
        findings: list[str] = []
        for bn in analytics.bottlenecks[:3]:
            mode = "manual task" if bn.is_manual else "automated step"
            findings.append(
                f"{bn.label} ({bn.lane_name}): risk index {bn.risk_score:.2f}, "
                f"betweenness {bn.betweenness:.2f}, {bn.handoff_pressure} incident handoff(s) ({mode})."
            )
        return findings

    @staticmethod
    def _build_rework_findings(analytics: GraphAnalytics) -> list[str]:
        if not analytics.cycles:
            return ["No rework cycles detected; execution paths are acyclic or exit cleanly on rejection."]
        findings: list[str] = []
        for idx, cyc in enumerate(analytics.cycles[:3], start=1):
            chain = " -> ".join(cyc.labels[:5])
            lanes = ", ".join(cyc.lanes_involved)
            findings.append(
                f"Loop #{idx} ({len(cyc.nodes)} nodes across {lanes}): {chain} -> return."
            )
        return findings

    @staticmethod
    def _build_recommendations(
        graph: ProcessGraph,
        analytics: GraphAnalytics,
    ) -> list[RecommendationItem]:
        recs: list[RecommendationItem] = []

        for idx, ai_rec in enumerate(graph.ai_recommendations[:3], start=1):
            recs.append(
                RecommendationItem(
                    priority="High" if idx == 1 else "Medium",
                    category="AI Architecture",
                    title=f"Suggested Enhancement #{idx}",
                    detail=ai_rec,
                )
            )

        # SLA / Wait optimization rule on critical path
        cp_set = set(analytics.critical_path)
        wait_on_cp = [n for n in graph.nodes if n.node_type == NodeType.WAIT and n.id in cp_set]
        if wait_on_cp:
            recs.append(
                RecommendationItem(
                    priority="High",
                    category="SLA & Wait Optimization",
                    title=f"Reduce wait latency on '{wait_on_cp[0].label}'",
                    detail=(
                        f"Wait state '{wait_on_cp[0].label}' sits directly on the critical path. "
                        "Introduce event-driven webhooks, escalation timers, or parallel pre-processing to compress cycle time."
                    ),
                    target_nodes=[n.id for n in wait_on_cp[:3]],
                )
            )

        top_manual = next((b for b in analytics.bottlenecks if b.is_manual and b.risk_score >= 0.35), None)
        if top_manual:
            recs.append(
                RecommendationItem(
                    priority="High",
                    category="Automation",
                    title=f"Mitigate bottleneck at '{top_manual.label}'",
                    detail=(
                        f"Manual step '{top_manual.label}' ({top_manual.lane_name}) concentrates high betweenness "
                        f"(risk {top_manual.risk_score:.2f}). Consider automated pre-validation, business rules, or RPA."
                    ),
                    target_nodes=[top_manual.node_id],
                )
            )

        if analytics.handoff_ratio > 0.55:
            recs.append(
                RecommendationItem(
                    priority="Medium",
                    category="Handoff Reduction",
                    title="Reduce cross-department handoff friction",
                    detail=(
                        f"{round(analytics.handoff_ratio * 100)}% of transitions cross swimlanes. "
                        "Consolidating adjacent validations and adding automated queue SLAs will reduce idle wait time."
                    ),
                )
            )

        if analytics.cycles:
            cyc = analytics.cycles[0]
            recs.append(
                RecommendationItem(
                    priority="High",
                    category="Rework Elimination",
                    title="Apply shift-left validation on detected rework cycle",
                    detail=(
                        f"A rework loop spans {', '.join(cyc.lanes_involved)}. "
                        "Adding upfront form/schema validation at entry reduces costly return iterations."
                    ),
                    target_nodes=cyc.nodes[:4],
                )
            )

        if analytics.automation_ratio < 0.35:
            recs.append(
                RecommendationItem(
                    priority="Medium",
                    category="Digital Transformation",
                    title="Increase end-to-end automation coverage",
                    detail=(
                        f"Only {round(analytics.automation_ratio * 100)}% of operational steps are automated. "
                        "Prioritize API integrations and event-driven notifications along the critical path."
                    ),
                    target_nodes=analytics.critical_path[:3],
                )
            )

        high_anomalies = [a for a in analytics.anomalies if a.severity == "high"]
        if high_anomalies:
            recs.append(
                RecommendationItem(
                    priority="High",
                    category="Structural Integrity",
                    title=f"Resolve {len(high_anomalies)} structural anomaly(ies)",
                    detail=high_anomalies[0].message,
                    target_nodes=[a.node_id for a in high_anomalies[:3]],
                )
            )

        if not recs:
            recs.append(
                RecommendationItem(
                    priority="Low",
                    category="Governance",
                    title="Instrument cycle-time telemetry",
                    detail="Workflow topology is structurally sound. Track actual p50/p95 durations on critical path nodes.",
                    target_nodes=analytics.critical_path[:3],
                )
            )

        return recs[:6]
