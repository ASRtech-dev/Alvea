"""Deterministic Mermaid.js v3.0 compiler, reverse parser, and XSS-hardened validator."""

from __future__ import annotations

import re
from collections import deque

from alvea.models import (
    ActorKind,
    ActorLane,
    Direction,
    NodeType,
    ProcessEdge,
    ProcessGraph,
    ProcessNode,
    ValidationResult,
    sanitize_identifier,
    sanitize_label_text,
)

CORPORATE_CLASSDEFS: tuple[str, ...] = (
    "classDef standard fill:#f8fafc,stroke:#94a3b8,stroke-width:1.5px,color:#0f172a,rx:8,ry:8;",
    "classDef startNode fill:#dcfce7,stroke:#16a34a,stroke-width:2px,color:#14532d,rx:20,ry:20;",
    "classDef endNode fill:#fee2e2,stroke:#dc2626,stroke-width:2px,color:#7f1d1d,rx:20,ry:20;",
    "classDef endSuccess fill:#dcfce7,stroke:#15803d,stroke-width:2px,color:#14532d,rx:20,ry:20;",
    "classDef decision fill:#fef9c3,stroke:#d97706,stroke-width:2px,color:#713f12;",
    "classDef systemNode fill:#e0f2fe,stroke:#0284c7,stroke-width:1.8px,color:#0c4a6e;",
    "classDef subprocessNode fill:#ede9fe,stroke:#7c3aed,stroke-width:1.8px,color:#3b0764;",
    "classDef waitNode fill:#fff7ed,stroke:#ea580c,stroke-width:1.8px,color:#7c2d12;",
    "classDef gatewayNode fill:#ccfbf1,stroke:#0d9488,stroke-width:2px,color:#134e4a;",
    "classDef criticalNode fill:#eef2ff,stroke:#4338ca,stroke-width:3px,color:#1e1b4b,rx:8,ry:8;",
)

# Strict security blocking (init directives with optional spaces + semicolon-chained click)
DANGEROUS_DIRECTIVE_RE = re.compile(r"(?:^\s*%%\{|(?:^|;)\s*click\b)", re.IGNORECASE)
XSS_PAYLOAD_RE = re.compile(
    r"(?i)(?:<(?:script|iframe|object|embed|svg|img|style|details|a|math|form|link|meta)\b|\bon[a-z]+\s*=|(?:javascript|vbscript)\s*:|data\s*:\s*text/html)"
)
HEADER_RE = re.compile(r"^\s*(?:graph|flowchart)\s+(LR|RL|TD|TB|BT)\b", re.IGNORECASE)
SUBGRAPH_RE = re.compile(r'^\s*subgraph\s+([A-Za-z0-9_\-]+)(?:\s*\[\s*"?([^"\]]+)"?\s*\])?\s*$')
END_RE = re.compile(r"^\s*end\s*$")

EDGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*--\s*"([^"]+)"\s*-->\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*-\.\s*"([^"]+)"\s*\.->\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*==\s*"([^"]+)"\s*==>\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*(?:-->|-\.->|==>)\s*\|"?([^"|]+)"?\|\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*--\s*([^->\n]+?)\s*-->\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*(?:-->|-\.->|==>)\s*([A-Za-z0-9_\-]+)\s*$'),
)

# Balanced node delimiters covering all 9 NodeTypes (including (), [] inside quotes)
NODE_DEF_RE = re.compile(
    r'^\s*([A-Za-z0-9_\-]+)\s*'
    r'(?:'
    r'(\(\[)"([^"]+)"(\]\))'
    r'|(\[\()"([^"]+)"(\)\])'
    r'|(\[\[)"([^"]+)"(\]\])'
    r'|(\(\()"([^"]+)"(\)\))'
    r'|(\{\{)"([^"]+)"(\}\})'
    r'|(>)"([^"]+)"(\])'
    r'|(\()"([^"]+)"(\))'
    r'|(\[)"([^"]+)"(\])'
    r'|(\{)"([^"]+)"(\})'
    r'|(\(\[)([^\]\)]+)(\]\))'
    r'|(\[\()([^\]\)]+)(\)\])'
    r'|(\[\[)([^\]]+)(\]\])'
    r'|(\{\{)([^\}]+)(\}\})'
    r'|(>)([^\]]+)(\])'
    r'|(\[)([^\]]+)(\])'
    r'|(\{)([^\}]+)(\})'
    r'|(\()([^\)]+)(\))'
    r')'
    r'(?::::([A-Za-z0-9_]+))?\s*$'
)

INLINE_EDGE_SPLIT_RE = re.compile(
    r'^(?P<lhs>.+?)\s*(?P<arrow>--\s*"[^"]+"\s*-->|-\.\s*"[^"]+"\s*\.->|==\s*"[^"]+"\s*==>|\s*(?:-->|-\.->|==>)\s*\|[^|]+\||-->|-\.->|==>)\s*(?P<rhs>.+)$'
)


def _match_node_def(stmt: str) -> tuple[str, str, str, str, str | None] | None:
    m = NODE_DEF_RE.match(stmt)
    if not m:
        return None
    nid = m.group(1)
    groups = m.groups()
    cls_name = groups[-1]
    body = groups[1:-1]
    for i in range(0, len(body), 3):
        if body[i] is not None:
            return nid, body[i], body[i + 1], body[i + 2], cls_name
    return None


def _mermaid_safe_label(raw: str, max_len: int = 80) -> str:
    cleaned = sanitize_label_text(raw, max_len=max_len)
    return cleaned.replace(">=", "≥").replace("<=", "≤")


def strip_security_threats(raw_code: str) -> tuple[str, list[str]]:
    """Mandatory anti-XSS sanitization applied unconditionally (even with auto_repair=False)."""
    warnings: list[str] = []
    safe_lines: list[str] = []
    for line in (raw_code or "").splitlines():
        stripped = line.strip()
        if DANGEROUS_DIRECTIVE_RE.search(stripped):
            warnings.append("Removed unsafe Mermaid directive (click/init).")
            continue
        if XSS_PAYLOAD_RE.search(line):
            cleaned_line = re.sub(r"(?i)<[^>]+>", "", line)
            cleaned_line = re.sub(r"(?i)(?:javascript|vbscript)\s*:", "", cleaned_line)
            cleaned_line = re.sub(r"(?i)data\s*:\s*text/html", "", cleaned_line)
            cleaned_line = re.sub(r"(?i)\bon[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+)", "", cleaned_line)
            warnings.append("Sanitized potentially unsafe HTML/JS payload.")
            safe_lines.append(cleaned_line)
        else:
            safe_lines.append(line)
    return "\n".join(safe_lines), list(dict.fromkeys(warnings))


class MermaidGenerator:
    """Compiles a typed ProcessGraph into executive Mermaid.js syntax with semantic shapes."""

    def render(
        self,
        graph: ProcessGraph,
        *,
        direction: Direction | None = None,
        highlight_critical: bool = False,
        critical_path: list[str] | None = None,
    ) -> str:
        dir_val = (direction or graph.direction).value
        critical_set = set(critical_path or []) if highlight_critical else set()
        critical_edges: set[tuple[str, str]] = set()
        if highlight_critical and critical_path and len(critical_path) >= 2:
            critical_edges = set(zip(critical_path, critical_path[1:]))

        ordered_lanes = self._order_lanes_by_depth(graph)
        nodes_by_lane: dict[str, list[ProcessNode]] = {lane.id: [] for lane in ordered_lanes}
        for node in graph.nodes:
            nodes_by_lane.setdefault(node.lane_id, []).append(node)

        lines: list[str] = [
            f"graph {dir_val}",
            "    %% ALVEA v3.0 — Corporate Semantic Styles",
            *(f"    {cdef}" for cdef in CORPORATE_CLASSDEFS),
            "",
        ]

        for lane in ordered_lanes:
            lane_nodes = nodes_by_lane.get(lane.id, [])
            if not lane_nodes:
                continue
            safe_lane_name = _mermaid_safe_label(lane.name, max_len=64)
            lines.append(f'    subgraph {lane.id}["{safe_lane_name}"]')
            for node in lane_nodes:
                lines.append(f"        {self._format_node(node, node.id in critical_set)}")
            lines.append("    end")
            lines.append("")

        lines.append("    %% Control Flow, Decisions, Parallelism & Loops")
        critical_link_indices: list[int] = []
        for idx, edge in enumerate(graph.edges):
            if (edge.source, edge.target) in critical_edges:
                critical_link_indices.append(idx)
            lines.append(f"    {self._format_edge(edge)}")

        if critical_link_indices:
            lines.append("")
            lines.append("    %% Critical Path Highlight (NetworkX)")
            idx_csv = ",".join(str(i) for i in critical_link_indices)
            lines.append(f"    linkStyle {idx_csv} stroke:#4338ca,stroke-width:3px;")

        return "\n".join(lines).strip()

    @staticmethod
    def _format_node(node: ProcessNode, is_critical: bool) -> str:
        lbl = _mermaid_safe_label(node.label, max_len=78)
        nt = node.node_type
        if nt == NodeType.START:
            return f'{node.id}(["{lbl}"]):::{"criticalNode" if is_critical else "startNode"}'
        if nt == NodeType.END_REJECT:
            return f'{node.id}(["{lbl}"]):::endNode'
        if nt == NodeType.END_SUCCESS:
            return f'{node.id}(["{lbl}"]):::{"criticalNode" if is_critical else "endSuccess"}'
        if nt == NodeType.DECISION:
            return f'{node.id}{{"{lbl}"}}:::{"criticalNode" if is_critical else "decision"}'
        if nt == NodeType.SYSTEM:
            return f'{node.id}[("{lbl}")]:::{"criticalNode" if is_critical else "systemNode"}'
        if nt == NodeType.SUBPROCESS:
            return f'{node.id}[["{lbl}"]]:::{"criticalNode" if is_critical else "subprocessNode"}'
        if nt == NodeType.WAIT:
            return f'{node.id}>"{lbl}"]:::{"criticalNode" if is_critical else "waitNode"}'
        if nt == NodeType.PARALLEL:
            return f'{node.id}{{{{"{lbl}"}}}}:::{"criticalNode" if is_critical else "gatewayNode"}'
        return f'{node.id}["{lbl}"]:::{"criticalNode" if is_critical else "standard"}'

    @staticmethod
    def _format_edge(edge: ProcessEdge) -> str:
        if edge.is_loop:
            if edge.label:
                return f'{edge.source} -. "{_mermaid_safe_label(edge.label, 40)}" .-> {edge.target}'
            return f"{edge.source} -.-> {edge.target}"
        if edge.is_parallel:
            if edge.label:
                return f'{edge.source} == "{_mermaid_safe_label(edge.label, 40)}" ==> {edge.target}'
            return f"{edge.source} ==> {edge.target}"
        if edge.label:
            return f'{edge.source} -- "{_mermaid_safe_label(edge.label, 40)}" --> {edge.target}'
        return f"{edge.source} --> {edge.target}"

    @staticmethod
    def _order_lanes_by_depth(graph: ProcessGraph) -> list[ActorLane]:
        adj: dict[str, list[str]] = {}
        for edge in graph.edges:
            adj.setdefault(edge.source, []).append(edge.target)

        starts = [n.id for n in graph.nodes if n.node_type == NodeType.START]
        if not starts and graph.nodes:
            starts = [graph.nodes[0].id]

        depth: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque((s, 0) for s in starts)
        while queue:
            nid, d = queue.popleft()
            if nid in depth:
                continue
            depth[nid] = d
            for nxt in adj.get(nid, []):
                if nxt not in depth:
                    queue.append((nxt, d + 1))

        lane_depth: dict[str, int] = {}
        for node in graph.nodes:
            d = depth.get(node.id, 999)
            lane_depth[node.lane_id] = min(lane_depth.get(node.lane_id, 999), d)

        return sorted(graph.lanes, key=lambda ln: (lane_depth.get(ln.id, 999), ln.order))


class MermaidValidator:
    """Validates, sanitizes against XSS, and repairs Mermaid syntax deterministically."""

    def validate_and_repair(
        self,
        raw_code: str,
        *,
        force_direction: Direction | None = None,
    ) -> ValidationResult:
        errors: list[str] = []
        warnings: list[str] = []
        repairs: list[str] = []

        extracted = self._extract_mermaid_code(raw_code)
        if extracted != (raw_code or "").strip():
            repairs.append("Extracted Mermaid block from Markdown/text wrapper.")

        cleaned, sec_warnings = strip_security_threats(extracted)
        if sec_warnings:
            warnings.extend(sec_warnings)
            repairs.append("Applied anti-XSS sanitization.")

        raw_lines = cleaned.splitlines()
        out_lines: list[str] = []
        has_header = False
        open_subgraphs = 0
        has_classdefs = False

        for line in raw_lines:
            stripped = line.strip()
            if not stripped:
                out_lines.append("")
                continue

            m_hdr = HEADER_RE.match(stripped)
            if m_hdr:
                has_header = True
                dir_token = force_direction.value if force_direction else m_hdr.group(1).upper()
                if dir_token == "TB":
                    dir_token = "TD"
                out_lines.append(f"graph {dir_token}")
                continue

            if stripped.startswith("%%"):
                out_lines.append(f"    {stripped}")
                continue

            if stripped.startswith("classDef "):
                has_classdefs = True
                out_lines.append(f"    {stripped}")
                continue

            if stripped.startswith(("linkStyle ", "style ", "class ")):
                out_lines.append(f"    {stripped}")
                continue

            m_sub = SUBGRAPH_RE.match(stripped)
            if m_sub:
                open_subgraphs += 1
                sub_id = sanitize_identifier(m_sub.group(1), prefix="L")
                sub_title = _mermaid_safe_label(m_sub.group(2) or sub_id, max_len=64)
                out_lines.append(f'    subgraph {sub_id}["{sub_title}"]')
                continue

            if END_RE.match(stripped):
                if open_subgraphs > 0:
                    open_subgraphs -= 1
                    out_lines.append("    end")
                else:
                    warnings.append("Removed orphan 'end' without matching subgraph.")
                    repairs.append("Removed orphan 'end'.")
                continue

            repaired_line = self._repair_statement(stripped, repairs)
            indent = "        " if open_subgraphs > 0 else "    "
            out_lines.append(f"{indent}{repaired_line}")

        if not has_header:
            dir_val = force_direction.value if force_direction else "LR"
            out_lines.insert(0, f"graph {dir_val}")
            repairs.append(f"Added missing 'graph {dir_val}' header.")

        if not has_classdefs:
            for cdef in reversed(CORPORATE_CLASSDEFS):
                out_lines.insert(1, f"    {cdef}")
            repairs.append("Injected corporate semantic classDefs.")

        while open_subgraphs > 0:
            out_lines.append("    end")
            open_subgraphs -= 1
            repairs.append("Closed unclosed subgraph with 'end'.")

        repaired_code = "\n".join(out_lines).strip()

        has_content = any(
            ("-->" in ln or "-.->" in ln or ".->" in ln or "==>" in ln or _match_node_def(ln.strip()) is not None)
            for ln in out_lines
        )
        if not has_content:
            errors.append("Mermaid code contains no valid nodes or transitions.")

        return ValidationResult(
            is_valid=len(errors) == 0,
            repaired_code=repaired_code,
            errors=errors,
            warnings=list(dict.fromkeys(warnings)),
            repairs_applied=list(dict.fromkeys(repairs)),
        )

    @staticmethod
    def _extract_mermaid_code(raw: str) -> str:
        text = (raw or "").strip()
        m_fence = re.search(r"```(?:mermaid)?\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
        if m_fence:
            return m_fence.group(1).strip()
        m_start = re.search(
            r"(?:^|\n)((?:graph|flowchart)\s+(?:LR|TD|TB|RL|BT)\b.*)",
            text,
            re.DOTALL | re.IGNORECASE,
        )
        if m_start:
            return m_start.group(1).strip()
        return text

    @staticmethod
    def _repair_statement(stmt: str, repairs: list[str]) -> str:
        if re.search(r"\s->\s", stmt) and "-->" not in stmt and ".->" not in stmt and "==>" not in stmt:
            stmt = re.sub(r"\s->\s", " --> ", stmt)
            repairs.append("Normalized single arrow '->' to '-->'.")

        m_pipe = re.match(r'^([A-Za-z0-9_\-]+)\s*(-->|-\.->|==>)\s*\|"?([^"|]+)"?\|\s*([A-Za-z0-9_\-]+)$', stmt)
        if m_pipe:
            src, arrow, lbl, tgt = m_pipe.groups()
            safe_lbl = _mermaid_safe_label(lbl, max_len=44)
            if arrow == "-.->":
                return f'{src} -. "{safe_lbl}" .-> {tgt}'
            if arrow == "==>":
                return f'{src} == "{safe_lbl}" ==> {tgt}'
            return f'{src} -- "{safe_lbl}" --> {tgt}'

        m_quoted_edge = re.match(r'^([A-Za-z0-9_\-]+)\s*--\s*"([^"]+)"\s*-->\s*([A-Za-z0-9_\-]+)$', stmt)
        if m_quoted_edge:
            src, lbl, tgt = m_quoted_edge.groups()
            return f'{src} -- "{_mermaid_safe_label(lbl, max_len=44)}" --> {tgt}'

        m_unquoted_edge = re.match(r'^([A-Za-z0-9_\-]+)\s*--\s*([^"\n]+?)\s*-->\s*([A-Za-z0-9_\-]+)$', stmt)
        if m_unquoted_edge:
            src, lbl, tgt = m_unquoted_edge.groups()
            return f'{src} -- "{_mermaid_safe_label(lbl, max_len=44)}" --> {tgt}'

        parsed_node = _match_node_def(stmt)
        if parsed_node is not None:
            nid, open_b, raw_lbl, close_b, cls_name = parsed_node
            safe_lbl = _mermaid_safe_label(raw_lbl, max_len=84)
            cls_part = f":::{cls_name}" if cls_name else ""
            return f'{nid}{open_b}"{safe_lbl}"{close_b}{cls_part}'

        return stmt


class MermaidParser:
    """Reverse parser: converts Mermaid syntax (all 9 node shapes + inline nodes) to ProcessGraph."""

    def parse(self, code: str, *, title: str | None = None) -> ProcessGraph:
        validator = MermaidValidator()
        val = validator.validate_and_repair(code)
        lines = val.repaired_code.splitlines()

        direction = Direction.LR
        lanes: dict[str, ActorLane] = {}
        nodes: dict[str, ProcessNode] = {}
        edges: list[ProcessEdge] = []
        current_lane_id: str | None = None

        def register_node(parsed_node: tuple[str, str, str, str, str | None]) -> str:
            nid, open_b, lbl, _close_b, cls_name = parsed_node
            clean_id = sanitize_identifier(nid, prefix="N")
            lane_id = current_lane_id or "GENERAL"
            if lane_id not in lanes:
                lanes[lane_id] = ActorLane(id=lane_id, name="General Workflow", kind=ActorKind.DEPARTMENT, order=len(lanes))
            ntype = self._infer_node_type(open_b, lbl, cls_name)
            is_auto = (
                ntype in (NodeType.SYSTEM, NodeType.PARALLEL)
                or lanes[lane_id].kind == ActorKind.SYSTEM
                or bool(re.search(r"automati|system|api|database|erp|digital|notif|transfer|autom[aá]tic", lbl, re.I))
            )
            dur_w = (
                0.5 if ntype in (NodeType.END_SUCCESS, NodeType.END_REJECT, NodeType.PARALLEL)
                else (1.0 if ntype == NodeType.SYSTEM or is_auto else (3.5 if ntype == NodeType.WAIT else (4.0 if ntype == NodeType.SUBPROCESS else (1.5 if ntype == NodeType.DECISION else 2.5))))
            )
            nodes[clean_id] = ProcessNode(
                id=clean_id,
                label=lbl,
                node_type=ntype,
                lane_id=lane_id,
                is_automated=is_auto,
                duration_weight=dur_w,
            )
            return clean_id

        for raw_line in lines:
            line = raw_line.strip()
            if not line or line.startswith(("%%", "classDef ", "linkStyle ", "style ", "class ")):
                continue

            m_hdr = HEADER_RE.match(line)
            if m_hdr:
                d = m_hdr.group(1).upper()
                direction = Direction.TD if d in ("TD", "TB") else Direction.LR
                continue

            m_sub = SUBGRAPH_RE.match(line)
            if m_sub:
                sub_id = sanitize_identifier(m_sub.group(1), prefix="L")
                sub_name = sanitize_label_text(m_sub.group(2) or sub_id, max_len=64)
                kind = (
                    ActorKind.SYSTEM
                    if re.search(r"system|app|platform|erp|portal|bot|api|database|sistema", sub_name, re.I)
                    else ActorKind.DEPARTMENT
                )
                if sub_id not in lanes:
                    lanes[sub_id] = ActorLane(id=sub_id, name=sub_name, kind=kind, order=len(lanes))
                current_lane_id = sub_id
                continue

            if END_RE.match(line):
                current_lane_id = None
                continue

            edge_parsed = self._try_parse_edge(line)
            if edge_parsed is not None:
                edges.append(edge_parsed)
                continue

            m_inline = INLINE_EDGE_SPLIT_RE.match(line)
            if m_inline:
                lhs_raw = m_inline.group("lhs").strip()
                arrow_raw = m_inline.group("arrow").strip()
                rhs_raw = m_inline.group("rhs").strip()

                lhs_node = _match_node_def(lhs_raw)
                rhs_node = _match_node_def(rhs_raw)
                src_id = register_node(lhs_node) if lhs_node else sanitize_identifier(lhs_raw, prefix="N")
                tgt_id = register_node(rhs_node) if rhs_node else sanitize_identifier(rhs_raw, prefix="N")

                rebuilt = f"{src_id} {arrow_raw} {tgt_id}"
                edge_inline = self._try_parse_edge(rebuilt)
                if edge_inline is not None:
                    edges.append(edge_inline)
                    continue

            parsed_node = _match_node_def(line)
            if parsed_node is not None:
                register_node(parsed_node)

        if not lanes:
            lanes["GENERAL"] = ActorLane(id="GENERAL", name="General Workflow", kind=ActorKind.DEPARTMENT, order=0)
        default_lane_id = next(iter(lanes.keys()))
        for edge in edges:
            for endpoint in (edge.source, edge.target):
                if endpoint not in nodes:
                    nodes[endpoint] = ProcessNode(
                        id=endpoint,
                        label=endpoint.replace("_", " "),
                        node_type=NodeType.TASK,
                        lane_id=default_lane_id,
                    )

        if not nodes:
            nodes["N1"] = ProcessNode(id="N1", label="Process Start", node_type=NodeType.START, lane_id=default_lane_id)

        return ProcessGraph(
            title=title or "Business Process Workflow",
            direction=direction,
            lanes=list(lanes.values()),
            nodes=list(nodes.values()),
            edges=edges,
        )

    @staticmethod
    def _try_parse_edge(line: str) -> ProcessEdge | None:
        is_dotted = "-." in line
        is_parallel = "==" in line
        for pat in EDGE_PATTERNS:
            m = pat.match(line)
            if not m:
                continue
            groups = m.groups()
            if len(groups) == 3:
                src, lbl, tgt = groups
                return ProcessEdge(
                    source=src,
                    target=tgt,
                    label=lbl.strip(),
                    is_conditional=not is_parallel,
                    is_parallel=is_parallel,
                    is_loop=is_dotted,
                )
            if len(groups) == 2:
                src, tgt = groups
                return ProcessEdge(source=src, target=tgt, is_parallel=is_parallel, is_loop=is_dotted)
        return None

    @staticmethod
    def _infer_node_type(open_b: str, label: str, cls_name: str | None) -> NodeType:
        cls_low = (cls_name or "").lower()
        lbl_low = label.lower()
        if cls_low == "startnode" or lbl_low.startswith(("start", "inicio")):
            return NodeType.START
        if cls_low == "endsuccess" or (
            lbl_low.startswith(("end", "fin"))
            and any(w in lbl_low for w in ("complet", "success", "resolved", "paid", "approved", "éxito", "exito", "desembols"))
        ):
            return NodeType.END_SUCCESS
        if cls_low == "endnode" or lbl_low.startswith(("end", "fin")):
            return NodeType.END_REJECT if any(w in lbl_low for w in ("reject", "cancel", "deny", "archiv", "rechaz", "deneg")) else NodeType.END_SUCCESS
        if cls_low == "gatewaynode" or open_b == "{{":
            return NodeType.PARALLEL
        if cls_low == "decision" or open_b == "{" or label.strip().endswith("?"):
            return NodeType.DECISION
        if cls_low == "systemnode" or open_b == "[(":
            return NodeType.SYSTEM
        if cls_low == "subprocessnode" or open_b == "[[":
            return NodeType.SUBPROCESS
        if cls_low == "waitnode" or open_b == ">":
            return NodeType.WAIT
        return NodeType.TASK
