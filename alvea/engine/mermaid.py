"""Generador determinista, parser inverso y validador/sanitizador anti-XSS de Mermaid.js."""

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
    "classDef criticalNode fill:#eef2ff,stroke:#4338ca,stroke-width:3px,color:#1e1b4b,rx:8,ry:8;",
)

# Bloqueo estricto de directivas peligrosas (incluye espacios tras %%{ y sentencias ; click)
DANGEROUS_DIRECTIVE_RE = re.compile(r"(?:^\s*%%\{|(?:^|;)\s*click\b)", re.IGNORECASE)
XSS_PAYLOAD_RE = re.compile(
    r"(?i)(?:<(?:script|iframe|object|embed|svg|img|style|details|a|math|form|link|meta)\b|\bon[a-z]+\s*=|(?:javascript|vbscript)\s*:|data\s*:\s*text/html)"
)
HEADER_RE = re.compile(r"^\s*(?:graph|flowchart)\s+(LR|RL|TD|TB|BT)\b", re.IGNORECASE)
SUBGRAPH_RE = re.compile(r'^\s*subgraph\s+([A-Za-z0-9_\-]+)(?:\s*\[\s*"?([^"\]]+)"?\s*\])?\s*$')
END_RE = re.compile(r"^\s*end\s*$")

# Aristas Mermaid: A --> B, A -- "lbl" --> B, A -->|lbl| B, A -. "lbl" .-> B, A -.->|lbl| B
EDGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*--\s*"([^"]+)"\s*-->\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*-\.\s*"([^"]+)"\s*\.->\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*(?:-->|-\.->)\s*\|"?([^"|]+)"?\|\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*--\s*([^->\n]+?)\s*-->\s*([A-Za-z0-9_\-]+)\s*$'),
    re.compile(r'^\s*([A-Za-z0-9_\-]+)\s*(?:-->|-\.->|==>)\s*([A-Za-z0-9_\-]+)\s*$'),
)

# Definición de nodo con soporte para etiquetas entrecomilladas que contengan (), [] o {}
NODE_DEF_RE = re.compile(
    r'^\s*([A-Za-z0-9_\-]+)\s*'
    r'(?:'
    r'(\(\[)"([^"]+)"(\]\))'
    r'|(\[\[)"([^"]+)"(\]\])'
    r'|(\(\()"([^"]+)"(\)\))'
    r'|(\{\{)"([^"]+)"(\}\})'
    r'|(\()"([^"]+)"(\))'
    r'|(\[)"([^"]+)"(\])'
    r'|(\{)"([^"]+)"(\})'
    r'|(\(\[)([^\]\)]+)(\]\))'
    r'|(\[\[)([^\]]+)(\]\])'
    r'|(\[)([^\]]+)(\])'
    r'|(\{)([^\}]+)(\})'
    r'|(\()([^\)]+)(\))'
    r')'
    r'(?::::([A-Za-z0-9_]+))?\s*$'
)

# Separador para detectar aristas con nodos definidos inline (ej. A["Inicio"] --> B{"¿Ok?"})
INLINE_EDGE_SPLIT_RE = re.compile(
    r'^(?P<lhs>.+?)\s*(?P<arrow>--\s*"[^"]+"\s*-->|-\.\s*"[^"]+"\s*\.->|(?:-->|-\.->)\s*\|[^|]+\||-->|-\.->|==>)\s*(?P<rhs>.+)$'
)


def _match_node_def(stmt: str) -> tuple[str, str, str, str, str | None] | None:
    """Devuelve (node_id, open_delim, label, close_delim, class_name) o None."""
    m = NODE_DEF_RE.match(stmt)
    if not m:
        return None
    nid = m.group(1)
    cls_name = m.group(38)
    groups = m.groups()[1:37]
    for i in range(0, len(groups), 3):
        if groups[i] is not None:
            return nid, groups[i], groups[i + 1], groups[i + 2], cls_name
    return None


def _mermaid_safe_label(raw: str, max_len: int = 80) -> str:
    """Sanitiza y normaliza operadores >= / <= a ≥ / ≤ para evitar que Mermaid strict mutile '>'."""
    cleaned = sanitize_label_text(raw, max_len=max_len)
    cleaned = cleaned.replace(">=", "≥").replace("<=", "≤")
    return cleaned


def strip_security_threats(raw_code: str) -> tuple[str, list[str]]:
    """Sanitización obligatoria anti-XSS (se aplica SIEMPRE, incluso con auto_repair=False)."""
    warnings: list[str] = []
    safe_lines: list[str] = []
    for line in (raw_code or "").splitlines():
        stripped = line.strip()
        if DANGEROUS_DIRECTIVE_RE.search(stripped):
            warnings.append("Directiva Mermaid potencialmente insegura eliminada (click/init).")
            continue
        if XSS_PAYLOAD_RE.search(line):
            cleaned_line = re.sub(r"(?i)<[^>]+>", "", line)
            cleaned_line = re.sub(r"(?i)(?:javascript|vbscript)\s*:", "", cleaned_line)
            cleaned_line = re.sub(r"(?i)data\s*:\s*text/html", "", cleaned_line)
            cleaned_line = re.sub(r"(?i)\bon[a-z]+\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s\"'>]+)", "", cleaned_line)
            warnings.append("Contenido HTML/JS potencialmente peligroso sanitizado.")
            safe_lines.append(cleaned_line)
        else:
            safe_lines.append(line)
    return "\n".join(safe_lines), list(dict.fromkeys(warnings))


class MermaidGenerator:
    """Compila un ProcessGraph tipado a sintaxis Mermaid v10 válida y ejecutiva."""

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
            "    %% ALVEA — Estilos Corporativos Semánticos",
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

        lines.append("    %% Flujo Secuencial, Bifurcaciones y Bucles")
        critical_link_indices: list[int] = []
        for idx, edge in enumerate(graph.edges):
            if (edge.source, edge.target) in critical_edges:
                critical_link_indices.append(idx)
            lines.append(f"    {self._format_edge(edge)}")

        if critical_link_indices:
            lines.append("")
            lines.append("    %% Resaltado de Camino Crítico (NetworkX)")
            idx_csv = ",".join(str(i) for i in critical_link_indices)
            lines.append(f"    linkStyle {idx_csv} stroke:#4338ca,stroke-width:3px;")

        return "\n".join(lines).strip()

    @staticmethod
    def _format_node(node: ProcessNode, is_critical: bool) -> str:
        lbl = _mermaid_safe_label(node.label, max_len=78)
        if node.node_type == NodeType.START:
            cls = "criticalNode" if is_critical else "startNode"
            return f'{node.id}(["{lbl}"]):::{cls}'
        if node.node_type == NodeType.END_REJECT:
            return f'{node.id}(["{lbl}"]):::endNode'
        if node.node_type == NodeType.END_SUCCESS:
            cls = "criticalNode" if is_critical else "endSuccess"
            return f'{node.id}(["{lbl}"]):::{cls}'
        if node.node_type == NodeType.DECISION:
            cls = "criticalNode" if is_critical else "decision"
            return f'{node.id}{{"{lbl}"}}:::{cls}'
        if node.node_type == NodeType.SUBPROCESS:
            cls = "criticalNode" if is_critical else "standard"
            return f'{node.id}[["{lbl}"]]:::{cls}'
        cls = "criticalNode" if is_critical else "standard"
        return f'{node.id}["{lbl}"]:::{cls}'

    @staticmethod
    def _format_edge(edge: ProcessEdge) -> str:
        if edge.is_loop:
            if edge.label:
                lbl = _mermaid_safe_label(edge.label, max_len=40)
                return f'{edge.source} -. "{lbl}" .-> {edge.target}'
            return f"{edge.source} -.-> {edge.target}"
        if edge.label:
            lbl = _mermaid_safe_label(edge.label, max_len=40)
            return f'{edge.source} -- "{lbl}" --> {edge.target}'
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
    """Valida, sanitiza contra XSS y repara automáticamente sintaxis Mermaid."""

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
            repairs.append("Bloque Mermaid extraído de envoltorio Markdown/texto.")

        cleaned, sec_warnings = strip_security_threats(extracted)
        if sec_warnings:
            warnings.extend(sec_warnings)
            repairs.append("Sanitización anti-XSS aplicada.")

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
                    warnings.append("Se eliminó un 'end' huérfano sin subgraph abierto.")
                    repairs.append("Eliminado 'end' huérfano.")
                continue

            repaired_line = self._repair_statement(stripped, repairs)
            indent = "        " if open_subgraphs > 0 else "    "
            out_lines.append(f"{indent}{repaired_line}")

        if not has_header:
            dir_val = force_direction.value if force_direction else "LR"
            out_lines.insert(0, f"graph {dir_val}")
            repairs.append(f"Cabecera 'graph {dir_val}' añadida automáticamente.")

        if not has_classdefs:
            for cdef in reversed(CORPORATE_CLASSDEFS):
                out_lines.insert(1, f"    {cdef}")
            repairs.append("Estilos corporativos classDef inyectados.")

        while open_subgraphs > 0:
            out_lines.append("    end")
            open_subgraphs -= 1
            repairs.append("Subgraph sin cerrar completado con 'end'.")

        repaired_code = "\n".join(out_lines).strip()

        has_content = any(
            ("-->" in ln or "-.->" in ln or ".->" in ln or _match_node_def(ln.strip()) is not None)
            for ln in out_lines
        )
        if not has_content:
            errors.append("El código Mermaid no contiene nodos ni transiciones válidas.")

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
        if re.search(r"\s->\s", stmt) and "-->" not in stmt and ".->" not in stmt:
            stmt = re.sub(r"\s->\s", " --> ", stmt)
            repairs.append("Flecha simple '->' normalizada a '-->'.")

        m_pipe = re.match(r'^([A-Za-z0-9_\-]+)\s*(-->|-\.->)\s*\|"?([^"|]+)"?\|\s*([A-Za-z0-9_\-]+)$', stmt)
        if m_pipe:
            src, arrow, lbl, tgt = m_pipe.groups()
            safe_lbl = _mermaid_safe_label(lbl, max_len=44)
            if arrow == "-.->":
                return f'{src} -. "{safe_lbl}" .-> {tgt}'
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
    """Parser inverso: convierte sintaxis Mermaid (incl. nodos inline) en ProcessGraph."""

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
                lanes[lane_id] = ActorLane(id=lane_id, name="Proceso General", kind=ActorKind.DEPARTMENT, order=len(lanes))
            ntype = self._infer_node_type(open_b, lbl, cls_name)
            is_auto = lanes[lane_id].kind == ActorKind.SYSTEM or bool(
                re.search(r"autom[aá]tic|sistema|api|bur[oó]|digital|notific|transfer", lbl, re.I)
            )
            dur_w = (
                0.5
                if ntype in (NodeType.END_SUCCESS, NodeType.END_REJECT)
                else (1.0 if is_auto else (1.5 if ntype == NodeType.DECISION else 2.5))
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
                    if re.search(r"sistema|app|plataforma|erp|portal|bot|api|system", sub_name, re.I)
                    else ActorKind.DEPARTMENT
                )
                if sub_id not in lanes:
                    lanes[sub_id] = ActorLane(id=sub_id, name=sub_name, kind=kind, order=len(lanes))
                current_lane_id = sub_id
                continue

            if END_RE.match(line):
                current_lane_id = None
                continue

            # 1. Arista estándar entre IDs
            edge_parsed = self._try_parse_edge(line)
            if edge_parsed is not None:
                edges.append(edge_parsed)
                continue

            # 2. Arista con definiciones inline de nodos (ej. A["Inicio"] --> B{"¿Ok?"})
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

            # 3. Definición aislada de nodo
            parsed_node = _match_node_def(line)
            if parsed_node is not None:
                register_node(parsed_node)

        if not lanes:
            lanes["GENERAL"] = ActorLane(id="GENERAL", name="Proceso General", kind=ActorKind.DEPARTMENT, order=0)
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
            nodes["N1"] = ProcessNode(id="N1", label="Inicio del proceso", node_type=NodeType.START, lane_id=default_lane_id)

        return ProcessGraph(
            title=title or "Arquitectura de Proceso",
            direction=direction,
            lanes=list(lanes.values()),
            nodes=list(nodes.values()),
            edges=edges,
        )

    @staticmethod
    def _try_parse_edge(line: str) -> ProcessEdge | None:
        is_dotted = "-." in line
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
                    is_conditional=True,
                    is_loop=is_dotted,
                )
            if len(groups) == 2:
                src, tgt = groups
                return ProcessEdge(source=src, target=tgt, is_loop=is_dotted)
        return None

    @staticmethod
    def _infer_node_type(open_b: str, label: str, cls_name: str | None) -> NodeType:
        cls_low = (cls_name or "").lower()
        lbl_low = label.lower()
        if cls_low == "startnode" or lbl_low.startswith(("inicio", "start")):
            return NodeType.START
        if cls_low == "endsuccess" or (
            lbl_low.startswith(("fin", "end"))
            and any(w in lbl_low for w in ("éxito", "exito", "exitosa", "complet", "desembols", "resuelto", "liquid", "recibido", "aprob", "success"))
        ):
            return NodeType.END_SUCCESS
        if cls_low == "endnode" or lbl_low.startswith(("fin", "end")):
            return NodeType.END_REJECT if any(w in lbl_low for w in ("rechaz", "archiv", "cancel", "deneg", "reject")) else NodeType.END_SUCCESS
        if cls_low == "decision" or open_b in ("{", "{{") or label.strip().endswith("?"):
            return NodeType.DECISION
        if open_b == "[[":
            return NodeType.SUBPROCESS
        return NodeType.TASK
