"""Modelos de dominio tipados de ALVEA (Pydantic v2)."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field, SecretStr, field_validator, model_validator

MERMAID_RESERVED = frozenset({
    "end",
    "graph",
    "subgraph",
    "flowchart",
    "style",
    "class",
    "classdef",
    "click",
    "linkstyle",
    "direction",
})


def sanitize_identifier(raw: str, prefix: str = "N") -> str:
    """Normaliza un identificador a formato ASCII seguro para Mermaid."""
    cleaned = re.sub(r"[^A-Za-z0-9_]", "_", (raw or "").strip())
    cleaned = re.sub(r"_+", "_", cleaned).strip("_")
    if not cleaned or not cleaned[0].isalpha():
        cleaned = f"{prefix}_{cleaned}" if cleaned else f"{prefix}_1"
    if cleaned.lower() in MERMAID_RESERVED:
        cleaned = f"{cleaned}_id"
    return cleaned[:40]


def sanitize_label_text(raw: str, max_len: int = 96) -> str:
    """Elimina etiquetas HTML peligrosas y normaliza saltos de línea y comillas."""
    text = str(raw or "").strip()
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"</?[a-zA-Z][^>]*>", "", text)
    text = re.sub(r"(?i)javascript\s*:", "", text)
    text = re.sub(r"(?i)vbscript\s*:", "", text)
    text = re.sub(r"(?i)data\s*:\s*text/html", "", text)
    text = text.replace('"', "'").replace("\r", " ").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text or "Actividad"


class Direction(StrEnum):
    LR = "LR"
    TD = "TD"


class ActorKind(StrEnum):
    HUMAN = "human"
    SYSTEM = "system"
    DEPARTMENT = "department"
    EXTERNAL = "external"


class NodeType(StrEnum):
    START = "start"
    TASK = "task"
    DECISION = "decision"
    SUBPROCESS = "subprocess"
    END_SUCCESS = "end_success"
    END_REJECT = "end_reject"


class ActorLane(BaseModel):
    id: str = Field(..., min_length=1, max_length=40)
    name: str = Field(..., min_length=1, max_length=70)
    kind: ActorKind = ActorKind.DEPARTMENT
    order: int = 0

    @field_validator("id", mode="before")
    @classmethod
    def _clean_id(cls, v: Any) -> str:
        return sanitize_identifier(str(v), prefix="L")

    @field_validator("name", mode="before")
    @classmethod
    def _clean_name(cls, v: Any) -> str:
        return sanitize_label_text(str(v), max_len=70)


class ProcessNode(BaseModel):
    id: str = Field(..., min_length=1, max_length=40)
    label: str = Field(..., min_length=1, max_length=100)
    node_type: NodeType = NodeType.TASK
    lane_id: str = Field(..., min_length=1, max_length=40)
    is_automated: bool = False
    duration_weight: float = Field(default=1.5, ge=0.1, le=1000.0)
    estimated_duration_min: float | None = Field(default=None, ge=0.0)
    risk_level: Literal["low", "medium", "high"] = "low"
    source_clause: str | None = Field(default=None, max_length=240)

    @field_validator("id", mode="before")
    @classmethod
    def _clean_id(cls, v: Any) -> str:
        return sanitize_identifier(str(v), prefix="N")

    @field_validator("lane_id", mode="before")
    @classmethod
    def _clean_lane(cls, v: Any) -> str:
        return sanitize_identifier(str(v), prefix="L")

    @field_validator("label", mode="before")
    @classmethod
    def _clean_label(cls, v: Any) -> str:
        return sanitize_label_text(str(v), max_len=96)


class ProcessEdge(BaseModel):
    source: str = Field(..., min_length=1, max_length=40)
    target: str = Field(..., min_length=1, max_length=40)
    label: str | None = Field(default=None, max_length=48)
    is_conditional: bool = False
    is_loop: bool = False

    @field_validator("source", "target", mode="before")
    @classmethod
    def _clean_endpoints(cls, v: Any) -> str:
        return sanitize_identifier(str(v), prefix="N")

    @field_validator("label", mode="before")
    @classmethod
    def _clean_edge_label(cls, v: Any) -> str | None:
        if v is None:
            return None
        cleaned = sanitize_label_text(str(v), max_len=44)
        return cleaned if cleaned and cleaned != "Actividad" else None


class ProcessGraph(BaseModel):
    title: str = Field(default="Proceso de Negocio", min_length=1, max_length=120)
    objective: str = Field(default="", max_length=280)
    language: Literal["es", "en"] = "es"
    direction: Direction = Direction.LR
    lanes: list[ActorLane] = Field(..., min_length=1, max_length=16)
    nodes: list[ProcessNode] = Field(..., min_length=1, max_length=80)
    edges: list[ProcessEdge] = Field(default_factory=list, max_length=200)
    ai_summary: str | None = Field(default=None, max_length=600)
    ai_recommendations: list[str] = Field(default_factory=list, max_length=8)

    @field_validator("title", mode="before")
    @classmethod
    def _clean_title(cls, v: Any) -> str:
        return sanitize_label_text(str(v), max_len=120)

    @model_validator(mode="after")
    def _ensure_integrity(self) -> "ProcessGraph":
        # 1. Deduplicar carriles y crear los que falten
        lane_map: dict[str, ActorLane] = {}
        for idx, lane in enumerate(self.lanes):
            if lane.id not in lane_map:
                lane.order = idx
                lane_map[lane.id] = lane

        for node in self.nodes:
            if node.lane_id not in lane_map:
                friendly = node.lane_id.replace("L_", "").replace("ACT_", "").replace("_", " ").title()
                lane_map[node.lane_id] = ActorLane(
                    id=node.lane_id,
                    name=friendly or "General",
                    kind=ActorKind.DEPARTMENT,
                    order=len(lane_map),
                )
        self.lanes = list(lane_map.values())

        # 2. Deduplicar nodos preservando orden
        node_map: dict[str, ProcessNode] = {}
        for node in self.nodes:
            if node.id not in node_map:
                node_map[node.id] = node
        self.nodes = list(node_map.values())

        # 3. Filtrar aristas inválidas (autorreferencias o inexistentes) y deduplicar
        valid_edges: list[ProcessEdge] = []
        seen: set[tuple[str, str, str | None]] = set()
        for edge in self.edges:
            if edge.source == edge.target:
                continue
            if edge.source not in node_map or edge.target not in node_map:
                continue
            key = (edge.source, edge.target, edge.label)
            if key not in seen:
                seen.add(key)
                valid_edges.append(edge)
        self.edges = valid_edges
        return self


class CycleInfo(BaseModel):
    nodes: list[str]
    labels: list[str]
    feedback_edge: tuple[str, str] | None = None
    lanes_involved: list[str] = Field(default_factory=list)


class BottleneckInfo(BaseModel):
    node_id: str
    label: str
    lane_name: str
    betweenness: float
    in_degree: int
    out_degree: int
    handoff_pressure: int
    risk_score: float
    is_manual: bool


class AnomalyInfo(BaseModel):
    kind: Literal["orphan", "dead_end", "incomplete_decision", "unreachable", "empty_lane"]
    node_id: str
    message: str
    severity: Literal["high", "medium", "low"]


class LaneMetric(BaseModel):
    lane_id: str
    lane_name: str
    kind: str
    node_count: int
    workload_pct: float
    automated_count: int
    handoffs_in: int
    handoffs_out: int


class GraphAnalytics(BaseModel):
    node_count: int
    edge_count: int
    lane_count: int
    decision_count: int
    cyclomatic_complexity: int
    complexity_level: Literal["Baja", "Moderada", "Alta"]
    automation_ratio: float
    handoff_count: int
    handoff_ratio: float
    efficiency_grade: str
    critical_path: list[str]
    critical_path_labels: list[str]
    critical_path_weight: float
    cycles: list[CycleInfo]
    bottlenecks: list[BottleneckInfo]
    anomalies: list[AnomalyInfo]
    lane_metrics: list[LaneMetric]


class CognitiveAnalysis(BaseModel):
    phase_a_actors: list[dict[str, Any]]
    phase_b_decisions: list[str]
    phase_c_routes: str


class RecommendationItem(BaseModel):
    priority: Literal["Alta", "Media", "Baja"]
    category: str
    title: str
    detail: str
    target_nodes: list[str] = Field(default_factory=list)


class ExecutiveReport(BaseModel):
    title: str
    summary: str
    efficiency_grade: str
    kpis: dict[str, Any]
    cognitive: CognitiveAnalysis
    lane_breakdown: list[LaneMetric]
    bottleneck_findings: list[str]
    rework_findings: list[str]
    anomalies: list[AnomalyInfo]
    recommendations: list[RecommendationItem]


class ValidationResult(BaseModel):
    is_valid: bool
    repaired_code: str
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    repairs_applied: list[str] = Field(default_factory=list)


# ─── Contratos API REST ────────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    text: str = Field(..., min_length=5, max_length=15_000)
    provider: str = Field(default="native_python", max_length=40)
    model: str | None = Field(default=None, max_length=120)
    direction: Direction = Direction.LR
    highlight_critical: bool = False
    title: str | None = Field(default=None, max_length=120)
    api_key: SecretStr | None = None
    base_url: str | None = Field(default=None, max_length=256)
    allow_native_fallback: bool = True


class ValidateMermaidRequest(BaseModel):
    code: str = Field(..., min_length=5, max_length=50_000)
    direction: Direction | None = None
    highlight_critical: bool = False
    auto_repair: bool = True
    title: str | None = Field(default=None, max_length=120)


class ExportRequest(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    mermaid: str | None = Field(default=None, max_length=50_000)
    text: str | None = Field(default=None, max_length=15_000)
    direction: Direction = Direction.LR
    diagram_png_base64: str | None = Field(default=None, max_length=2_500_000)


class ImportYamlRequest(BaseModel):
    yaml_content: str = Field(..., min_length=10, max_length=50_000)
