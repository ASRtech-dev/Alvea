"""ALVEA v3.1 Standard Operating Procedure (SOP) Topological Generator.

Transforms a validated ProcessGraph + NetworkX GraphAnalytics into an ISO-style
operational SOP document with:
  - Kahn priority-queue topological ordering over the condensed DAG
  - Hierarchical parallel track numbering (e.g., 3a, 3b) for Fork/Join scopes
  - Explicit rework loop references mapped to exact earlier step numbers
  - Roles & Responsibilities matrix, Decision Rules, Exception Handling, and SLA Controls
  - Sanitized Markdown renderer (XSS-safe)
"""

from __future__ import annotations

import hashlib
import heapq
import re
from datetime import datetime, timezone
from typing import Any

import networkx as nx

from alvea.engine.analytics import GraphAnalyzer
from alvea.models import (
    GraphAnalytics,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
    SOPBranchTarget,
    SOPDocument,
    SOPRoleMatrixRow,
    SOPStep,
    sanitize_label_text,
)


def _format_duration(minutes: float | None) -> str | None:
    if minutes is None or minutes <= 0:
        return None
    if minutes >= 480 and minutes % 480 == 0:
        days = int(minutes // 480)
        return f"{days} business day{'s' if days != 1 else ''}"
    if minutes >= 60:
        hours = minutes / 60.0
        if abs(hours - round(hours)) < 0.05:
            h_int = int(round(hours))
            return f"{h_int} hour{'s' if h_int != 1 else ''}"
        return f"{hours:.1f} hours"
    if minutes < 1:
        return f"{int(round(minutes * 60))} sec"
    return f"{int(round(minutes))} min"


def _execution_mode(node: ProcessNode) -> str:
    if node.node_type == NodeType.DECISION:
        return "Decision Gateway"
    if node.node_type == NodeType.WAIT:
        return "Wait / SLA"
    if node.node_type == NodeType.PARALLEL:
        return "Parallel Sync"
    if node.node_type in (NodeType.START, NodeType.END_SUCCESS, NodeType.END_REJECT):
        return "Milestone"
    if node.is_automated or node.node_type == NodeType.SYSTEM:
        return "Automated"
    return "Manual"


def _md_escape_cell(text: str) -> str:
    """Escapes Markdown table cells and strips any dangerous HTML/JS schemes."""
    cleaned = sanitize_label_text(text, max_len=240)
    cleaned = cleaned.replace("|", "\\|").replace("`", "'")
    return cleaned


def _md_escape_inline(text: str) -> str:
    """Sanitizes inline Markdown text against raw HTML/script injection."""
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"</?[a-zA-Z][^>]*>", "", cleaned)
    cleaned = re.sub(r"(?i)javascript\s*:", "", cleaned)
    cleaned = re.sub(r"(?i)vbscript\s*:", "", cleaned)
    cleaned = re.sub(r"(?i)data\s*:\s*text/html", "", cleaned)
    cleaned = cleaned.replace("\r", " ").replace("\n", " ")
    return re.sub(r"\s+", " ", cleaned).strip()


class SOPGenerator:
    """Deterministic ISO-style Standard Operating Procedure generator over ProcessGraph."""

    def generate(self, graph: ProcessGraph, analytics: GraphAnalytics) -> SOPDocument:
        node_by_id = {n.id: n for n in graph.nodes}
        lane_by_id = {ln.id: ln for ln in graph.lanes}
        node_index = {n.id: idx for idx, n in enumerate(graph.nodes)}
        critical_set = set(analytics.critical_path)

        # Build NetworkX DiGraph & isolate back-edges (rework loops)
        G = nx.DiGraph()
        for n in graph.nodes:
            G.add_node(n.id)
        for e in graph.edges:
            G.add_edge(e.source, e.target)

        back_edges = GraphAnalyzer._find_dfs_back_edges(G, graph)

        # Build acyclic condensation graph G_dag
        G_dag = G.copy()
        for u, v in list(back_edges):
            if G_dag.has_edge(u, v):
                G_dag.remove_edge(u, v)

        safety = 0
        while not nx.is_directed_acyclic_graph(G_dag) and safety < 50:
            safety += 1
            try:
                cyc = nx.find_cycle(G_dag, orientation="original")
                u, v, _ = cyc[-1]
                G_dag.remove_edge(u, v)
                back_edges.add((u, v))
            except nx.NetworkXNoCycle:
                break

        # Separate forward edges vs loop edges per source node
        forward_edges_by_src: dict[str, list[ProcessEdge]] = {n.id: [] for n in graph.nodes}
        loop_edges_by_src: dict[str, list[ProcessEdge]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            if edge.is_loop or (edge.source, edge.target) in back_edges:
                loop_edges_by_src[edge.source].append(edge)
            else:
                forward_edges_by_src[edge.source].append(edge)

        # Identify parallel fork -> branch scopes for hierarchical numbering (e.g. 3a, 3b)
        parallel_membership, fork_tracks = self._detect_parallel_scopes(G_dag, node_by_id, node_index)

        # Deterministic Kahn priority-queue topological sort
        ordered_ids = self._kahn_topological_order(G_dag, node_by_id, node_index)

        # Pass 1: Assign human-readable step numbers (1, 2, 3a, 3b, 4...)
        step_number_map = self._assign_step_numbers(ordered_ids, parallel_membership, fork_tracks)

        # Pass 2: Build full SOPStep objects with exact cross-step routing & loop references
        steps: list[SOPStep] = []
        decision_rules: list[dict[str, Any]] = []
        rework_and_exceptions: list[str] = []

        for nid in ordered_ids:
            node = node_by_id[nid]
            lane = lane_by_id[node.lane_id]
            step_no = step_number_map[nid]
            mode = _execution_mode(node)
            sla_str = _format_duration(node.estimated_duration_min)
            p_group = parallel_membership.get(nid, (None, None))[0]

            next_targets: list[SOPBranchTarget] = []
            for e in forward_edges_by_src.get(nid, []):
                tgt = node_by_id[e.target]
                cond = (e.label or "").strip() or ("Parallel track" if e.is_parallel else "Proceed")
                next_targets.append(
                    SOPBranchTarget(
                        condition=cond,
                        target_step=step_number_map.get(e.target, "?"),
                        target_label=tgt.label,
                        target_node_id=e.target,
                        is_loop=False,
                    )
                )

            loop_targets: list[SOPBranchTarget] = []
            for e in loop_edges_by_src.get(nid, []):
                tgt = node_by_id[e.target]
                cond = (e.label or "").strip() or "Rework / Correction Required"
                tgt_step = step_number_map.get(e.target, "?")
                loop_targets.append(
                    SOPBranchTarget(
                        condition=cond,
                        target_step=tgt_step,
                        target_label=tgt.label,
                        target_node_id=e.target,
                        is_loop=True,
                    )
                )
                rework_and_exceptions.append(
                    f"Step {step_no} ({node.label}): If '{cond}', return execution to Step {tgt_step} ({tgt.label})."
                )

            instruction = self._synthesize_instruction(
                node=node,
                lane_name=lane.name,
                mode=mode,
                sla_str=sla_str,
                next_targets=next_targets,
                loop_targets=loop_targets,
            )

            steps.append(
                SOPStep(
                    step_number=step_no,
                    node_id=nid,
                    title=node.label,
                    owner=lane.name,
                    owner_kind=lane.kind.value.capitalize(),
                    execution_mode=mode,  # type: ignore[arg-type]
                    instruction=instruction,
                    sla_display=sla_str,
                    is_critical_path=nid in critical_set,
                    parallel_group=p_group,
                    next_steps=next_targets,
                    rework_loops=loop_targets,
                )
            )

            if node.node_type == NodeType.DECISION or len(next_targets) + len(loop_targets) >= 2 and node.node_type != NodeType.PARALLEL:
                branches = [
                    {
                        "condition": b.condition,
                        "action": f"{'Return to' if b.is_loop else 'Proceed to'} Step {b.target_step} ({b.target_label})",
                        "is_loop": b.is_loop,
                    }
                    for b in [*next_targets, *loop_targets]
                ]
                decision_rules.append(
                    {
                        "step_number": step_no,
                        "gateway": node.label,
                        "owner": lane.name,
                        "branches": branches,
                    }
                )

            if node.node_type == NodeType.END_REJECT:
                rework_and_exceptions.append(
                    f"Step {step_no} ({node.label}): Terminal rejection/exception state owned by {lane.name}. Log reason code and close record."
                )

        # Roles & Responsibilities matrix
        roles_matrix = self._build_roles_matrix(graph, steps)

        # SLA & Quality Controls
        sla_controls = self._build_sla_controls(graph, analytics, steps)

        # Deterministic SOP ID based on process title
        title_hash = hashlib.sha1(graph.title.encode("utf-8")).hexdigest()[:4].upper()
        sop_id = f"SOP-{title_hash}"
        effective_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        if analytics.estimated_cycle_time_min is not None:
            cycle_str = _format_duration(analytics.estimated_cycle_time_min) or f"{analytics.estimated_cycle_time_min} min"
        else:
            cycle_str = f"{analytics.critical_path_weight} complexity pts ({len(analytics.critical_path)} critical steps)"

        start_labels = [s.title for s in steps if node_by_id[s.node_id].node_type == NodeType.START]
        end_labels = [
            s.title for s in steps if node_by_id[s.node_id].node_type in (NodeType.END_SUCCESS, NodeType.END_REJECT)
        ]
        lane_names = ", ".join(ln.name for ln in graph.lanes)
        purpose = (
            graph.objective.strip()
            if graph.objective and graph.objective.strip()
            else f"Standardize end-to-end execution, decision routing, and handoff accountability for '{graph.title}'."
        )
        scope = (
            f"Applies to {len(graph.lanes)} participating role(s)/system(s) ({lane_names}), "
            f"from initiation ({start_labels[0] if start_labels else steps[0].title}) "
            f"through completion ({', '.join(end_labels[:3]) if end_labels else steps[-1].title})."
        )

        if not rework_and_exceptions:
            rework_and_exceptions.append(
                "No explicit rework loops or rejection paths were modeled. Escalate unexpected exceptions to the primary process owner."
            )

        return SOPDocument(
            sop_id=sop_id,
            title=f"Standard Operating Procedure: {graph.title}",
            version="1.0",
            effective_date=effective_date,
            purpose=purpose,
            scope=scope,
            estimated_cycle_time=cycle_str,
            roles_and_responsibilities=roles_matrix,
            steps=steps,
            decision_rules=decision_rules,
            rework_and_exceptions=rework_and_exceptions,
            sla_and_controls=sla_controls,
        )

    @staticmethod
    def _kahn_topological_order(
        G_dag: nx.DiGraph,
        node_by_id: dict[str, ProcessNode],
        node_index: dict[str, int],
    ) -> list[str]:
        """Priority-queue Kahn sort prioritizing START nodes first, END nodes last, then source order."""
        in_deg = {n: G_dag.in_degree(n) for n in G_dag.nodes}

        def _prio(nid: str) -> tuple[int, int]:
            nt = node_by_id[nid].node_type
            rank = 0 if nt == NodeType.START else (2 if nt in (NodeType.END_SUCCESS, NodeType.END_REJECT) else 1)
            return (rank, node_index.get(nid, 999))

        heap: list[tuple[tuple[int, int], str]] = []
        for nid, deg in in_deg.items():
            if deg == 0:
                heapq.heappush(heap, (_prio(nid), nid))

        order: list[str] = []
        while heap:
            _, u = heapq.heappop(heap)
            order.append(u)
            for v in G_dag.successors(u):
                in_deg[v] -= 1
                if in_deg[v] == 0:
                    heapq.heappush(heap, (_prio(v), v))

        # Safety fallback for any residual unvisited nodes
        visited = set(order)
        for nid in sorted(G_dag.nodes, key=lambda x: node_index.get(x, 999)):
            if nid not in visited:
                order.append(nid)
        return order

    @staticmethod
    def _detect_parallel_scopes(
        G_dag: nx.DiGraph,
        node_by_id: dict[str, ProcessNode],
        node_index: dict[str, int],
    ) -> tuple[dict[str, tuple[str, int]], dict[str, int]]:
        """Maps nodes inside a PARALLEL fork..join scope to (fork_id, branch_idx)."""
        membership: dict[str, tuple[str, int]] = {}
        fork_tracks: dict[str, int] = {}

        forks = [
            nid
            for nid, node in node_by_id.items()
            if node.node_type == NodeType.PARALLEL and G_dag.out_degree(nid) >= 2
        ]
        for fork_id in sorted(forks, key=lambda x: node_index.get(x, 999)):
            succs = sorted(G_dag.successors(fork_id), key=lambda x: node_index.get(x, 999))
            if len(succs) < 2:
                continue
            # Find common convergence nodes reachable from all branches
            branch_reach = [({s} | nx.descendants(G_dag, s)) for s in succs]
            common_desc = set.intersection(*branch_reach) if branch_reach else set()

            fork_tracks[fork_id] = len(succs)
            for b_idx, start_node in enumerate(succs):
                # Nodes strictly on this branch before convergence
                branch_only = branch_reach[b_idx] - common_desc
                for bn in branch_only:
                    if bn not in membership and node_by_id[bn].node_type != NodeType.PARALLEL:
                        membership[bn] = (fork_id, b_idx)

        return membership, fork_tracks

    @staticmethod
    def _assign_step_numbers(
        ordered_ids: list[str],
        parallel_membership: dict[str, tuple[str, int]],
        fork_tracks: dict[str, int],
    ) -> dict[str, str]:
        """Assigns sequential numbers (1, 2, ...) and hierarchical letters (3a, 3b, 3a.2) for parallel tracks."""
        step_numbers: dict[str, str] = {}
        major = 0
        fork_base_major: dict[str, int] = {}
        branch_subcount: dict[tuple[str, int], int] = {}

        for nid in ordered_ids:
            if nid in parallel_membership:
                fork_id, branch_idx = parallel_membership[nid]
                if fork_id not in fork_base_major:
                    major += 1
                    fork_base_major[fork_id] = major
                base = fork_base_major[fork_id]
                letter = chr(ord("a") + (branch_idx % 26))
                sub_key = (fork_id, branch_idx)
                branch_subcount[sub_key] = branch_subcount.get(sub_key, 0) + 1
                sub_idx = branch_subcount[sub_key]
                step_numbers[nid] = f"{base}{letter}" if sub_idx == 1 else f"{base}{letter}.{sub_idx}"
            else:
                major += 1
                step_numbers[nid] = str(major)

        return step_numbers

    @staticmethod
    def _synthesize_instruction(
        *,
        node: ProcessNode,
        lane_name: str,
        mode: str,
        sla_str: str | None,
        next_targets: list[SOPBranchTarget],
        loop_targets: list[SOPBranchTarget],
    ) -> str:
        sla_note = f" Target SLA: {sla_str}." if sla_str else ""
        if node.node_type == NodeType.START:
            return f"Process trigger initiated by {lane_name}: {node.label}.{sla_note}"
        if node.node_type == NodeType.END_SUCCESS:
            return f"Confirm all upstream deliverables are complete and close the workflow successfully ({node.label})."
        if node.node_type == NodeType.END_REJECT:
            return f"Record formal rejection/cancellation outcome ({node.label}), notify affected stakeholders, and archive."
        if node.node_type == NodeType.PARALLEL:
            if len(next_targets) >= 2:
                tracks = ", ".join(f"Step {t.target_step}" for t in next_targets)
                return f"Initiate concurrent execution across parallel tracks ({tracks}). Do not block independent branches."
            return f"Synchronization barrier ({node.label}): verify all preceding parallel tracks have completed before advancing."
        if node.node_type == NodeType.WAIT:
            return f"{lane_name} monitors waiting state: {node.label}.{sla_note} Escalate if SLA threshold is exceeded."
        if node.node_type == NodeType.DECISION:
            routes = [f"If '{t.condition}' -> Step {t.target_step}" for t in next_targets]
            routes.extend(f"If '{t.condition}' -> Return to Step {t.target_step}" for t in loop_targets)
            route_txt = "; ".join(routes) if routes else "route according to policy criteria"
            return f"{lane_name} evaluates '{node.label}' and routes execution: {route_txt}.{sla_note}"
        if mode == "Automated":
            return f"Automated execution by {lane_name}: {node.label}. Verify system audit log and output status.{sla_note}"
        return f"{lane_name} executes '{node.label}' and verifies completeness before handoff.{sla_note}"

    @staticmethod
    def _build_roles_matrix(graph: ProcessGraph, steps: list[SOPStep]) -> list[SOPRoleMatrixRow]:
        rows: list[SOPRoleMatrixRow] = []
        steps_by_owner: dict[str, list[SOPStep]] = {ln.name: [] for ln in graph.lanes}
        for step in steps:
            steps_by_owner.setdefault(step.owner, []).append(step)

        for lane in graph.lanes:
            owned = steps_by_owner.get(lane.name, [])
            step_nums = [s.step_number for s in owned]
            auto_cnt = sum(1 for s in owned if s.execution_mode == "Automated")
            titles_preview = ", ".join(s.title for s in owned[:3])
            if len(owned) > 3:
                titles_preview += f" (+{len(owned) - 3} more)"
            summary = titles_preview if titles_preview else "Governance / Oversight"
            rows.append(
                SOPRoleMatrixRow(
                    role_name=lane.name,
                    role_kind=lane.kind.value.capitalize(),
                    step_numbers=step_nums,
                    step_count=len(owned),
                    automated_steps=auto_cnt,
                    responsibility_summary=summary,
                )
            )
        return rows

    @staticmethod
    def _build_sla_controls(
        graph: ProcessGraph,
        analytics: GraphAnalytics,
        steps: list[SOPStep],
    ) -> list[str]:
        controls: list[str] = []
        cp_steps = [s.step_number for s in steps if s.is_critical_path]
        if cp_steps:
            controls.append(
                f"Critical Path Monitoring: Steps {', '.join(cp_steps)} directly govern end-to-end cycle time "
                f"({f'{analytics.estimated_cycle_time_min} min' if analytics.estimated_cycle_time_min is not None else f'{analytics.critical_path_weight} pts'})."
            )

        timed_steps = [s for s in steps if s.sla_display]
        if timed_steps:
            sla_list = "; ".join(f"Step {s.step_number} ({s.sla_display})" for s in timed_steps[:6])
            controls.append(f"Explicit Step SLAs: {sla_list}.")

        if analytics.handoff_count > 0:
            controls.append(
                f"Inter-Role Handoffs: {analytics.handoff_count} cross-lane transition(s) ({round(analytics.handoff_ratio * 100)}% of edges). "
                "Require timestamped handoff receipts between departments."
            )

        if analytics.bottlenecks:
            top_b = analytics.bottlenecks[0]
            controls.append(
                f"Primary Bottleneck Control: Monitor '{top_b.label}' ({top_b.lane_name}, risk score {top_b.risk_score:.2f}) for queue buildup."
            )

        controls.append(
            f"Automation Baseline: {round(analytics.automation_ratio * 100)}% automated operational steps across {analytics.lane_count} role(s) "
            f"(Process Efficiency Grade: {analytics.efficiency_grade})."
        )
        return controls


def render_sop_markdown(sop: SOPDocument) -> str:
    """Renders a strictly sanitized ISO-style Markdown Standard Operating Procedure."""
    lines: list[str] = [
        f"# {_md_escape_inline(sop.title)}",
        "",
        "| Field | Value |",
        "| :--- | :--- |",
        f"| **Document ID** | `{_md_escape_cell(sop.sop_id)}` |",
        f"| **Version** | {_md_escape_cell(sop.version)} |",
        f"| **Effective Date** | {_md_escape_cell(sop.effective_date)} |",
        f"| **Estimated Cycle Time** | {_md_escape_cell(sop.estimated_cycle_time)} |",
        "",
        "## 1. Purpose & Scope",
        "",
        f"**Purpose:** {_md_escape_inline(sop.purpose)}",
        "",
        f"**Scope:** {_md_escape_inline(sop.scope)}",
        "",
        "## 2. Roles & Responsibilities",
        "",
        "| Role / System | Type | Assigned Steps | Automated | Primary Responsibilities |",
        "| :--- | :--- | :--- | :---: | :--- |",
    ]

    for row in sop.roles_and_responsibilities:
        steps_str = ", ".join(row.step_numbers) if row.step_numbers else "—"
        lines.append(
            f"| **{_md_escape_cell(row.role_name)}** | {_md_escape_cell(row.role_kind)} | "
            f"{_md_escape_cell(steps_str)} | {row.automated_steps}/{row.step_count} | "
            f"{_md_escape_cell(row.responsibility_summary)} |"
        )

    lines.extend([
        "",
        "## 3. Step-by-Step Operating Procedure",
        "",
        "| Step | Owner | Mode | Procedure & Routing | SLA |",
        "| :---: | :--- | :--- | :--- | :---: |",
    ])

    for step in sop.steps:
        step_tag = f"**{step.step_number}**" + (" ★" if step.is_critical_path else "")
        routing_parts: list[str] = []
        for nxt in step.next_steps:
            routing_parts.append(f"[{nxt.condition} -> Step {nxt.target_step}]")
        for lp in step.rework_loops:
            routing_parts.append(f"[LOOP: {lp.condition} -> Return to Step {lp.target_step}]")
        proc_cell = _md_escape_cell(step.instruction)
        if routing_parts:
            proc_cell += " " + _md_escape_cell(" ".join(routing_parts))
        sla_cell = _md_escape_cell(step.sla_display or "—")
        lines.append(
            f"| {step_tag} | {_md_escape_cell(step.owner)} | {_md_escape_cell(step.execution_mode)} | {proc_cell} | {sla_cell} |"
        )

    lines.append("")
    lines.append("_★ Indicates a step on the NetworkX Critical Path._")

    if sop.decision_rules:
        lines.extend([
            "",
            "## 4. Decision & Routing Matrix",
            "",
            "| Step | Decision Gateway | Owner | Routing Rules |",
            "| :---: | :--- | :--- | :--- |",
        ])
        for rule in sop.decision_rules:
            branches_str = "; ".join(
                f"{b['condition']} -> {b['action']}" for b in rule.get("branches", [])
            )
            lines.append(
                f"| **{rule.get('step_number', '?')}** | {_md_escape_cell(str(rule.get('gateway', '')))} | "
                f"{_md_escape_cell(str(rule.get('owner', '')))} | {_md_escape_cell(branches_str)} |"
            )

    lines.extend([
        "",
        "## 5. Exception Handling & Rework Loops",
        "",
    ])
    for exc_item in sop.rework_and_exceptions:
        lines.append(f"- {_md_escape_inline(exc_item)}")

    lines.extend([
        "",
        "## 6. SLA & Quality Controls",
        "",
    ])
    for ctrl in sop.sla_and_controls:
        lines.append(f"- {_md_escape_inline(ctrl)}")

    lines.append("")
    return "\n".join(lines)
