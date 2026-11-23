"""Motor de Analítica de Procesos con NetworkX 3.7.

Calcula ciclos de retrabajo, condensación DAG y camino crítico ponderado,
centralidad de intermediación (cuellos de botella), complejidad ciclomática
de McCabe, tasa de automatización, presión de handoffs y anomalías estructurales.
"""

from __future__ import annotations

import itertools
import networkx as nx

from alvea.models import (
    AnomalyInfo,
    BottleneckInfo,
    CycleInfo,
    GraphAnalytics,
    LaneMetric,
    NodeType,
    ProcessGraph,
)


class GraphAnalyzer:
    """Analizador estructural de grafos BPA basado en NetworkX."""

    MAX_CYCLES = 25

    def analyze(self, graph: ProcessGraph) -> GraphAnalytics:
        G = nx.DiGraph()
        lane_by_id = {ln.id: ln for ln in graph.lanes}
        node_by_id = {n.id: n for n in graph.nodes}

        for node in graph.nodes:
            G.add_node(
                node.id,
                label=node.label,
                lane_id=node.lane_id,
                node_type=node.node_type.value,
                is_automated=node.is_automated,
                duration_weight=node.duration_weight,
            )

        handoff_count = 0
        for edge in graph.edges:
            u_lane = node_by_id[edge.source].lane_id
            v_lane = node_by_id[edge.target].lane_id
            is_handoff = u_lane != v_lane
            if is_handoff:
                handoff_count += 1
            G.add_edge(
                edge.source,
                edge.target,
                label=edge.label or "",
                is_loop=edge.is_loop,
                is_handoff=is_handoff,
                weight=node_by_id[edge.target].duration_weight,
            )

        n_count = G.number_of_nodes()
        e_count = len(graph.edges)
        decision_count = sum(1 for n in graph.nodes if n.node_type == NodeType.DECISION)
        components = nx.number_weakly_connected_components(G) if n_count > 0 else 1

        # Complejidad ciclomática de McCabe: M = E - N + 2P (mínimo 1)
        cyclomatic = max(1, e_count - n_count + 2 * components)
        if cyclomatic <= 4:
            complexity_level = "Baja"
        elif cyclomatic <= 10:
            complexity_level = "Moderada"
        else:
            complexity_level = "Alta"

        # Ratio de automatización sobre tareas y decisiones
        operational_nodes = [
            n for n in graph.nodes if n.node_type in (NodeType.TASK, NodeType.DECISION, NodeType.SUBPROCESS)
        ]
        if operational_nodes:
            auto_ratio = round(
                sum(1 for n in operational_nodes if n.is_automated) / len(operational_nodes), 3
            )
        else:
            auto_ratio = 0.0

        handoff_ratio = round(min(1.0, handoff_count / e_count), 3) if e_count > 0 else 0.0

        # Detección de ciclos simples (acotada a MAX_CYCLES para estabilidad)
        raw_cycles = list(itertools.islice(nx.simple_cycles(G), self.MAX_CYCLES))
        raw_cycles.sort(key=len)

        back_edges = self._find_dfs_back_edges(G, graph)
        cycles: list[CycleInfo] = []
        for cyc in raw_cycles:
            cyc_edges = list(zip(cyc, cyc[1:] + [cyc[0]]))
            fb = next((e for e in cyc_edges if e in back_edges), cyc_edges[-1] if cyc_edges else None)
            lanes_in_cyc = list(dict.fromkeys(lane_by_id[node_by_id[nid].lane_id].name for nid in cyc))
            cycles.append(
                CycleInfo(
                    nodes=list(cyc),
                    labels=[node_by_id[nid].label for nid in cyc],
                    feedback_edge=fb,
                    lanes_involved=lanes_in_cyc,
                )
            )

        # Condensación a DAG y Camino Crítico ponderado
        critical_path, critical_weight = self._compute_critical_path(G, back_edges, node_by_id)
        critical_labels = [node_by_id[nid].label for nid in critical_path if nid in node_by_id]

        # Centralidad de intermediación y Cuellos de Botella
        bottlenecks = self._compute_bottlenecks(G, graph, lane_by_id)

        # Auditoría de anomalías estructurales
        anomalies = self._detect_anomalies(G, graph)

        # Métricas por carril
        lane_metrics = self._compute_lane_metrics(G, graph)

        # Calificación ejecutiva de eficiencia (A+ .. D)
        efficiency_grade = self._compute_efficiency_grade(
            auto_ratio=auto_ratio,
            handoff_ratio=handoff_ratio,
            cycle_count=len(cycles),
            anomaly_count=sum(1 for a in anomalies if a.severity == "high"),
            cyclomatic=cyclomatic,
        )

        return GraphAnalytics(
            node_count=n_count,
            edge_count=e_count,
            lane_count=len(graph.lanes),
            decision_count=decision_count,
            cyclomatic_complexity=cyclomatic,
            complexity_level=complexity_level,
            automation_ratio=auto_ratio,
            handoff_count=handoff_count,
            handoff_ratio=handoff_ratio,
            efficiency_grade=efficiency_grade,
            critical_path=critical_path,
            critical_path_labels=critical_labels,
            critical_path_weight=round(critical_weight, 2),
            cycles=cycles,
            bottlenecks=bottlenecks,
            anomalies=anomalies,
            lane_metrics=lane_metrics,
        )

    @staticmethod
    def _find_dfs_back_edges(G: nx.DiGraph, graph: ProcessGraph) -> set[tuple[str, str]]:
        """Identifica aristas de retorno mediante DFS desde los nodos de inicio."""
        back_edges: set[tuple[str, str]] = {
            (e.source, e.target) for e in graph.edges if e.is_loop
        }
        starts = [n.id for n in graph.nodes if n.node_type == NodeType.START]
        if not starts:
            starts = [n for n in G.nodes if G.in_degree(n) == 0] or list(G.nodes)[:1]

        state: dict[str, int] = {}  # 0=unvisited, 1=visiting, 2=done

        def dfs(u: str) -> None:
            state[u] = 1
            for v in G.successors(u):
                st = state.get(v, 0)
                if st == 1:
                    back_edges.add((u, v))
                elif st == 0:
                    dfs(v)
            state[u] = 2

        for s in starts:
            if state.get(s, 0) == 0:
                dfs(s)
        for n in G.nodes:
            if state.get(n, 0) == 0:
                dfs(n)

        return back_edges

    @staticmethod
    def _compute_critical_path(
        G: nx.DiGraph,
        back_edges: set[tuple[str, str]],
        node_by_id: dict,
    ) -> tuple[list[str], float]:
        if G.number_of_nodes() == 0:
            return [], 0.0

        G_dag = G.copy()
        for u, v in back_edges:
            if G_dag.has_edge(u, v):
                G_dag.remove_edge(u, v)

        # Garantizar DAG estricto si quedaran ciclos residuales
        safety = 0
        while not nx.is_directed_acyclic_graph(G_dag) and safety < 50:
            safety += 1
            try:
                cyc = nx.find_cycle(G_dag, orientation="original")
                u, v, _ = cyc[-1]
                G_dag.remove_edge(u, v)
            except nx.NetworkXNoCycle:
                break

        if not nx.is_directed_acyclic_graph(G_dag):
            return [], 0.0

        path = nx.dag_longest_path(G_dag, weight="weight")
        weight = sum(node_by_id[nid].duration_weight for nid in path if nid in node_by_id)
        return list(path), float(weight)

    @staticmethod
    def _compute_bottlenecks(
        G: nx.DiGraph,
        graph: ProcessGraph,
        lane_by_id: dict,
    ) -> list[BottleneckInfo]:
        if G.number_of_nodes() == 0:
            return []

        bc = nx.betweenness_centrality(G, normalized=True)
        degrees = {n: G.in_degree(n) + G.out_degree(n) for n in G.nodes}
        max_deg = max(degrees.values(), default=1) or 1

        candidates: list[BottleneckInfo] = []
        for node in graph.nodes:
            if node.node_type in (NodeType.START, NodeType.END_SUCCESS, NodeType.END_REJECT):
                continue
            in_d = G.in_degree(node.id)
            out_d = G.out_degree(node.id)
            handoff_p = sum(
                1 for _, _, d in G.in_edges(node.id, data=True) if d.get("is_handoff")
            ) + sum(
                1 for _, _, d in G.out_edges(node.id, data=True) if d.get("is_handoff")
            )
            bc_val = float(bc.get(node.id, 0.0))
            is_manual = not node.is_automated
            risk = round(
                min(1.0, bc_val * 0.52 + ((in_d + out_d) / max_deg) * 0.28 + (0.20 if is_manual else 0.0)),
                3,
            )
            candidates.append(
                BottleneckInfo(
                    node_id=node.id,
                    label=node.label,
                    lane_name=lane_by_id[node.lane_id].name,
                    betweenness=round(bc_val, 3),
                    in_degree=in_d,
                    out_degree=out_d,
                    handoff_pressure=handoff_p,
                    risk_score=risk,
                    is_manual=is_manual,
                )
            )

        candidates.sort(key=lambda b: (b.risk_score, b.betweenness, b.handoff_pressure), reverse=True)
        return candidates[:4]

    @staticmethod
    def _detect_anomalies(G: nx.DiGraph, graph: ProcessGraph) -> list[AnomalyInfo]:
        anomalies: list[AnomalyInfo] = []
        starts = [n.id for n in graph.nodes if n.node_type == NodeType.START]
        if not starts:
            starts = [n.id for n in graph.nodes if G.in_degree(n.id) == 0]

        reachable: set[str] = set()
        for s in starts:
            if s in G:
                reachable.add(s)
                reachable.update(nx.descendants(G, s))

        edge_out_counts: dict[str, int] = {}
        for edge in graph.edges:
            edge_out_counts[edge.source] = edge_out_counts.get(edge.source, 0) + 1

        nodes_per_lane: dict[str, int] = {ln.id: 0 for ln in graph.lanes}
        for node in graph.nodes:
            nodes_per_lane[node.lane_id] = nodes_per_lane.get(node.lane_id, 0) + 1
            in_d = G.in_degree(node.id)
            out_d = edge_out_counts.get(node.id, 0)

            if in_d == 0 and out_d == 0 and len(graph.nodes) > 1:
                anomalies.append(
                    AnomalyInfo(
                        kind="orphan",
                        node_id=node.id,
                        message=f"El nodo '{node.label}' está completamente desconectado del flujo.",
                        severity="high",
                    )
                )
            elif node.id not in reachable and len(graph.nodes) > 1:
                anomalies.append(
                    AnomalyInfo(
                        kind="unreachable",
                        node_id=node.id,
                        message=f"El nodo '{node.label}' no es alcanzable desde ningún inicio del proceso.",
                        severity="medium",
                    )
                )

            if out_d == 0 and node.node_type not in (NodeType.END_SUCCESS, NodeType.END_REJECT):
                anomalies.append(
                    AnomalyInfo(
                        kind="dead_end",
                        node_id=node.id,
                        message=f"'{node.label}' termina sin salida ni nodo de cierre explícito.",
                        severity="high",
                    )
                )

            if node.node_type == NodeType.DECISION and out_d < 2:
                anomalies.append(
                    AnomalyInfo(
                        kind="incomplete_decision",
                        node_id=node.id,
                        message=f"La decisión '{node.label}' solo tiene {out_d} rama(s) de salida (requiere ≥ 2).",
                        severity="high",
                    )
                )

        for lane in graph.lanes:
            if nodes_per_lane.get(lane.id, 0) == 0:
                anomalies.append(
                    AnomalyInfo(
                        kind="empty_lane",
                        node_id=lane.id,
                        message=f"El carril '{lane.name}' no contiene actividades asignadas.",
                        severity="low",
                    )
                )

        return anomalies

    @staticmethod
    def _compute_lane_metrics(G: nx.DiGraph, graph: ProcessGraph) -> list[LaneMetric]:
        total = max(1, len(graph.nodes))
        node_lane = {n.id: n.lane_id for n in graph.nodes}
        metrics: list[LaneMetric] = []

        for lane in graph.lanes:
            ln_nodes = [n for n in graph.nodes if n.lane_id == lane.id]
            h_in = sum(
                1 for u, v in G.edges() if node_lane.get(v) == lane.id and node_lane.get(u) != lane.id
            )
            h_out = sum(
                1 for u, v in G.edges() if node_lane.get(u) == lane.id and node_lane.get(v) != lane.id
            )
            metrics.append(
                LaneMetric(
                    lane_id=lane.id,
                    lane_name=lane.name,
                    kind=lane.kind.value,
                    node_count=len(ln_nodes),
                    workload_pct=round((len(ln_nodes) / total) * 100.0, 1),
                    automated_count=sum(1 for n in ln_nodes if n.is_automated),
                    handoffs_in=h_in,
                    handoffs_out=h_out,
                )
            )
        return metrics

    @staticmethod
    def _compute_efficiency_grade(
        *,
        auto_ratio: float,
        handoff_ratio: float,
        cycle_count: int,
        anomaly_count: int,
        cyclomatic: int,
    ) -> str:
        score = 82.0
        score += auto_ratio * 18.0
        score -= max(0.0, handoff_ratio - 0.45) * 28.0
        score -= cycle_count * 5.0
        score -= anomaly_count * 12.0
        if cyclomatic > 12:
            score -= 6.0

        if score >= 92:
            return "A+"
        if score >= 85:
            return "A"
        if score >= 78:
            return "A-"
        if score >= 70:
            return "B+"
        if score >= 62:
            return "B"
        if score >= 52:
            return "C+"
        return "C"
