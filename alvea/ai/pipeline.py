"""Pipeline unificado de generación con auto-reparación en 5 niveles y telemetría."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from alvea.ai.catalog import StructuredMode, get_model_spec, get_provider
from alvea.ai.prompts import (
    REPAIR_PROMPT,
    SYSTEM_PROMPT_COMPACT,
    SYSTEM_PROMPT_FULL,
    build_user_prompt,
)
from alvea.ai.providers import ProviderCallError, call_llm_provider
from alvea.engine.analytics import GraphAnalyzer
from alvea.engine.mermaid import (
    MermaidGenerator,
    MermaidParser,
    MermaidValidator,
    strip_security_threats,
)
from alvea.engine.nlp_parser import LocalBPAEngine
from alvea.engine.presets import match_preset_by_text
from alvea.engine.report import ReportBuilder
from alvea.models import Direction, ProcessGraph
from alvea.security import SSRFBlockedError

THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)


@dataclass
class PipelineOutcome:
    graph: ProcessGraph
    mermaid: str
    analytics: dict[str, Any]
    report: dict[str, Any]
    validation: dict[str, Any]
    meta: dict[str, Any]


def strip_reasoning_and_extract_json(raw_text: str) -> str:
    """Limpia bloques <think>...</think>, fences Markdown y extrae el objeto JSON."""
    cleaned = THINK_BLOCK_RE.sub("", raw_text or "").strip()
    m_fence = re.search(r"```(?:json)?\s*\n(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if m_fence:
        cleaned = m_fence.group(1).strip()

    start = cleaned.find("{")
    if start == -1:
        return cleaned

    # Extraer primer objeto balanceado {...}
    depth = 0
    in_str = False
    escape = False
    for idx in range(start, len(cleaned)):
        ch = cleaned[idx]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if not in_str:
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return cleaned[start : idx + 1]
    return cleaned[start:]


def repair_and_parse_json_dict(raw_text: str) -> dict[str, Any]:
    """Sanitizador JSON local tolerante a fallos comunes de LLMs pequeños."""
    candidate = strip_reasoning_and_extract_json(raw_text)
    candidate = candidate.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    # Corregir trailing commas antes de } o ]
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    # Corregir booleanos/None estilo Python SOLO como valores JSON (sin mutar strings como "True Positive")
    candidate = re.sub(r"(?<=[:\[,\s])\bTrue\b(?=\s*[,}\]])", "true", candidate)
    candidate = re.sub(r"(?<=[:\[,\s])\bFalse\b(?=\s*[,}\]])", "false", candidate)
    candidate = re.sub(r"(?<=[:\[,\s])\bNone\b(?=\s*[,}\]])", "null", candidate)

    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("La raíz JSON debe ser un objeto.")

    # Normalizar alias frecuentes de LLMs
    if "lanes" not in data:
        for alias in ("swimlanes", "actors", "carriles", "roles"):
            if alias in data and isinstance(data[alias], list):
                data["lanes"] = data.pop(alias)
                break
    if "nodes" not in data:
        for alias in ("steps", "tasks", "nodos", "activities"):
            if alias in data and isinstance(data[alias], list):
                data["nodes"] = data.pop(alias)
                break
    if "edges" not in data:
        for alias in ("transitions", "connections", "links", "aristas", "flows"):
            if alias in data and isinstance(data[alias], list):
                data["edges"] = data.pop(alias)
                break
    if "title" not in data and "process_name" in data:
        data["title"] = data.pop("process_name")
    if "ai_summary" not in data and "executive_summary" in data:
        data["ai_summary"] = data.pop("executive_summary")

    # Normalizar aristas from/to -> source/target y is_rework_loop -> is_loop
    for edge in data.get("edges") or []:
        if isinstance(edge, dict):
            if "source" not in edge and "from" in edge:
                edge["source"] = edge.pop("from")
            if "target" not in edge and "to" in edge:
                edge["target"] = edge.pop("to")
            if "is_loop" not in edge and "is_rework_loop" in edge:
                edge["is_loop"] = edge.pop("is_rework_loop")

    # Normalizar nodos end -> end_success/end_reject y automation_level -> is_automated
    for node in data.get("nodes") or []:
        if isinstance(node, dict):
            nt = str(node.get("node_type", "task")).lower()
            if nt == "end":
                lbl = str(node.get("label", "")).lower()
                node["node_type"] = "end_reject" if any(w in lbl for w in ("rechaz", "cancel", "archiv", "reject")) else "end_success"
            elif nt not in ("start", "task", "decision", "subprocess", "end_success", "end_reject"):
                node["node_type"] = "task"
            if "is_automated" not in node and "automation_level" in node:
                node["is_automated"] = str(node.get("automation_level")).lower() == "automated"

    # Normalizar lane role_type -> kind
    for lane in data.get("lanes") or []:
        if isinstance(lane, dict):
            if "kind" not in lane and "role_type" in lane:
                rt = str(lane.pop("role_type")).lower()
                lane["kind"] = "human" if rt in ("customer", "management") else (rt if rt in ("system", "department", "external") else "department")
            elif str(lane.get("kind", "")).lower() not in ("human", "system", "department", "external"):
                lane["kind"] = "department"

    # Normalizar ai_recommendations si vienen como objetos Recommendation
    if "ai_recommendations" not in data and isinstance(data.get("recommendations"), list):
        recs = []
        for r in data["recommendations"]:
            if isinstance(r, str):
                recs.append(r)
            elif isinstance(r, dict):
                txt = r.get("rationale") or r.get("detail") or r.get("title")
                if txt:
                    recs.append(str(txt))
        data["ai_recommendations"] = recs[:6]

    return data


class ProcessPipeline:
    """Orquestador principal de ALVEA: generación, validación, NetworkX y reporte."""

    def __init__(self) -> None:
        self.nlp_engine = LocalBPAEngine()
        self.mermaid_gen = MermaidGenerator()
        self.mermaid_val = MermaidValidator()
        self.mermaid_parser = MermaidParser()
        self.analyzer = GraphAnalyzer()
        self.report_builder = ReportBuilder()

    def generate(
        self,
        *,
        text: str,
        provider_id: str = "native_python",
        model_id: str | None = None,
        direction: Direction = Direction.LR,
        highlight_critical: bool = False,
        title: str | None = None,
        api_key: str | None = None,
        base_url: str | None = None,
        allow_native_fallback: bool = True,
    ) -> PipelineOutcome:
        t0 = time.perf_counter()
        provider = get_provider(provider_id)
        if provider is None:
            raise ProviderCallError(f"Proveedor desconocido: '{provider_id}'.", status_code=400)

        chosen_model = (model_id or provider.default_model or "alvea-bpa-v2").strip()
        stage = "native_python"
        fallback_notice: str | None = None

        if provider.protocol == "native":
            graph = self._run_native(text, direction=direction, title=title)
        else:
            try:
                graph, stage = self._run_llm_with_repair(
                    text=text,
                    provider=provider,
                    model_id=chosen_model,
                    direction=direction,
                    title=title,
                    api_key=api_key,
                    base_url=base_url,
                )
            except (ProviderCallError, SSRFBlockedError) as exc:
                if not allow_native_fallback or isinstance(exc, SSRFBlockedError) or getattr(exc, "status_code", 500) == 401:
                    raise
                graph = self._run_native(text, direction=direction, title=title)
                stage = "native_fallback"
                fallback_notice = f"Fallback automático al Motor Nativo Python ({exc})"

        graph.direction = direction
        if title:
            graph.title = title

        return self._finalize(
            graph=graph,
            direction=direction,
            highlight_critical=highlight_critical,
            provider_id=provider.id,
            provider_name=provider.name,
            model_id=chosen_model,
            stage=stage,
            fallback_notice=fallback_notice,
            started_at=t0,
        )

    def analyze_mermaid(
        self,
        *,
        code: str,
        direction: Direction | None = None,
        highlight_critical: bool = False,
        auto_repair: bool = True,
        title: str | None = None,
    ) -> PipelineOutcome:
        t0 = time.perf_counter()
        # La sanitización anti-XSS se aplica SIEMPRE, incluso con auto_repair=False
        safe_raw, sec_warnings = strip_security_threats(code)
        val = self.mermaid_val.validate_and_repair(safe_raw, force_direction=direction)
        if sec_warnings:
            val.warnings = list(dict.fromkeys([*val.warnings, *sec_warnings]))
        effective_code = val.repaired_code if auto_repair else safe_raw
        graph = self.mermaid_parser.parse(effective_code, title=title)
        target_dir = direction or graph.direction
        graph.direction = target_dir

        analytics = self.analyzer.analyze(graph)
        report = self.report_builder.build(graph, analytics)

        final_mermaid = (
            self.mermaid_gen.render(
                graph,
                direction=target_dir,
                highlight_critical=highlight_critical,
                critical_path=analytics.critical_path,
            )
            if (highlight_critical or direction is not None)
            else effective_code
        )

        elapsed_ms = round((time.perf_counter() - t0) * 1000, 1)
        return PipelineOutcome(
            graph=graph,
            mermaid=final_mermaid,
            analytics=analytics.model_dump(),
            report=report.model_dump(),
            validation=val.model_dump(),
            meta={
                "provider": "mermaid_editor",
                "provider_name": "Editor Mermaid + NetworkX",
                "model": "deterministic-parser",
                "stage": "repaired" if val.repairs_applied else "validated",
                "elapsed_ms": elapsed_ms,
                "fallback_notice": None,
            },
        )

    def _run_native(self, text: str, *, direction: Direction, title: str | None) -> ProcessGraph:
        preset = match_preset_by_text(text)
        if preset is not None:
            graph = preset.graph.model_copy(deep=True)
            graph.direction = direction
            if title:
                graph.title = title
            return graph
        return self.nlp_engine.parse(text, direction=direction, title=title)

    def _run_llm_with_repair(
        self,
        *,
        text: str,
        provider,
        model_id: str,
        direction: Direction,
        title: str | None,
        api_key: str | None,
        base_url: str | None,
    ) -> tuple[ProcessGraph, str]:
        model_spec = get_model_spec(provider, model_id)
        use_compact = bool(
            (model_spec and model_spec.compact_prompt)
            or re.search(r"[:\-_/](?:1|2|3|4|7|8|e4)b\b", model_id, re.I)
        )
        system_prompt = SYSTEM_PROMPT_COMPACT if use_compact else SYSTEM_PROMPT_FULL
        user_prompt = build_user_prompt(text, direction=direction.value)
        schema = ProcessGraph.model_json_schema()

        # Nivel 0 & Nivel 1: Modo estructurado con degradación automática
        initial_mode: StructuredMode = model_spec.structured_mode if model_spec else "json_object"
        modes_to_try: list[StructuredMode] = []
        for m in (initial_mode, "json_object", "prompt_only"):
            if m not in modes_to_try and m != "native":
                modes_to_try.append(m)

        raw_output = ""
        used_mode: StructuredMode = initial_mode
        last_err: Exception | None = None

        for mode in modes_to_try:
            try:
                raw_output, _ = call_llm_provider(
                    provider=provider,
                    model_id=model_id,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    json_schema=schema,
                    mode=mode,
                    api_key=api_key,
                    custom_base_url=base_url,
                )
                used_mode = mode
                break
            except ProviderCallError as exc:
                last_err = exc
                if not exc.retryable_mode:
                    raise
        else:
            if last_err:
                raise last_err

        cleaned_raw = THINK_BLOCK_RE.sub("", raw_output).strip()
        mermaid_hint_re = re.compile(r"(?:^|\n)\s*(?:graph|flowchart)\s+(?:LR|TD|TB|RL|BT)\b", re.I)

        # Nivel 2: Sanitizador JSON local + validación Pydantic
        try:
            parsed_dict = repair_and_parse_json_dict(raw_output)
            graph = ProcessGraph.model_validate(parsed_dict)
            if len(graph.nodes) >= 2 and len(graph.edges) == 0:
                raise ValueError("El grafo tiene nodos desconectados sin aristas válidas.")
            stage = "strict_json" if used_mode == "json_schema" else "sanitized_json"
            return graph, stage
        except (json.JSONDecodeError, ValueError, ValidationError) as parse_err:
            # Nivel 4 rápido: si el modelo devolvió Mermaid en vez de JSON, parsearlo directo sin gastar otra llamada
            if mermaid_hint_re.search(cleaned_raw):
                graph = self.mermaid_parser.parse(cleaned_raw, title=title)
                return graph, "mermaid_fallback"

            # Nivel 3: 1 único reintento de auto-reparación LLM (temperature=0.0) respetando used_mode
            repair_mode: StructuredMode = "json_object" if used_mode == "json_schema" else used_mode
            repaired_raw = ""
            try:
                repair_req = (
                    f"Error de validación:\n{str(parse_err)[:500]}\n\n"
                    f"JSON original a corregir:\n{cleaned_raw[:4000]}"
                )
                repaired_raw, _ = call_llm_provider(
                    provider=provider,
                    model_id=model_id,
                    system_prompt=REPAIR_PROMPT,
                    user_prompt=repair_req,
                    json_schema=schema,
                    mode=repair_mode,
                    api_key=api_key,
                    custom_base_url=base_url,
                    temperature=0.0,
                )
                parsed_dict = repair_and_parse_json_dict(repaired_raw)
                graph = ProcessGraph.model_validate(parsed_dict)
                if len(graph.nodes) >= 2 and len(graph.edges) == 0:
                    raise ValueError("El grafo reparado no contiene aristas válidas.")
                return graph, "llm_self_repaired"
            except Exception:
                cleaned_repaired = THINK_BLOCK_RE.sub("", repaired_raw).strip()
                if cleaned_repaired and mermaid_hint_re.search(cleaned_repaired):
                    return self.mermaid_parser.parse(cleaned_repaired, title=title), "mermaid_fallback"
                if mermaid_hint_re.search(cleaned_raw):
                    return self.mermaid_parser.parse(cleaned_raw, title=title), "mermaid_fallback"
                raise ProviderCallError(
                    f"El modelo '{model_id}' devolvió una estructura inválida tras la auto-reparación.",
                    status_code=502,
                ) from parse_err

    def _finalize(
        self,
        *,
        graph: ProcessGraph,
        direction: Direction,
        highlight_critical: bool,
        provider_id: str,
        provider_name: str,
        model_id: str,
        stage: str,
        fallback_notice: str | None,
        started_at: float,
    ) -> PipelineOutcome:
        analytics = self.analyzer.analyze(graph)
        report = self.report_builder.build(graph, analytics)
        mermaid_code = self.mermaid_gen.render(
            graph,
            direction=direction,
            highlight_critical=highlight_critical,
            critical_path=analytics.critical_path,
        )
        validation = self.mermaid_val.validate_and_repair(mermaid_code, force_direction=direction)
        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)

        return PipelineOutcome(
            graph=graph,
            mermaid=mermaid_code,
            analytics=analytics.model_dump(),
            report=report.model_dump(),
            validation=validation.model_dump(),
            meta={
                "provider": provider_id,
                "provider_name": provider_name,
                "model": model_id,
                "stage": stage,
                "elapsed_ms": elapsed_ms,
                "fallback_notice": fallback_notice,
            },
        )
