"""Unified ALVEA v3.0 workflow generation pipeline with 5-level self-repair and telemetry."""

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
from alvea.engine.report import ReportBuilder
from alvea.engine.sop import SOPGenerator
from alvea.engine.swimlane_svg import SwimlaneSVGRenderer
from alvea.models import Direction, ProcessGraph
from alvea.security import SSRFBlockedError

THINK_BLOCK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

VALID_NODE_TYPES = frozenset({
    "start", "task", "system", "subprocess", "wait", "decision", "parallel", "end_success", "end_reject"
})

NODE_TYPE_ALIASES = {
    "service": "system",
    "api": "system",
    "automated": "system",
    "bot": "system",
    "database": "system",
    "delay": "wait",
    "timer": "wait",
    "queue": "wait",
    "sla": "wait",
    "approval_wait": "wait",
    "gateway": "decision",
    "branch": "decision",
    "condition": "decision",
    "fork": "parallel",
    "join": "parallel",
}


@dataclass
class PipelineOutcome:
    graph: ProcessGraph
    swimlane_svg: str
    mermaid: str
    analytics: dict[str, Any]
    report: dict[str, Any]
    sop: dict[str, Any]
    validation: dict[str, Any]
    meta: dict[str, Any]


def _coerce_duration_minutes(val: Any) -> float | None:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val) if val >= 0 else None
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(s|m|h|d|w)?", str(val).strip(), re.I)
    if not m:
        return None
    num = float(m.group(1).replace(",", "."))
    if num < 0:
        return None
    unit = (m.group(2) or "m").lower()
    if unit == "w":
        return round(num * 2400.0, 1)
    if unit == "d":
        return round(num * 480.0, 1)
    if unit == "h":
        return round(num * 60.0, 1)
    if unit == "s":
        return round(max(0.1, num / 60.0), 2)
    return round(num, 1)


def strip_reasoning_and_extract_json(raw_text: str) -> str:
    """Strips <think>...</think> blocks, Markdown fences, and extracts the first balanced JSON object."""
    cleaned = THINK_BLOCK_RE.sub("", raw_text or "").strip()
    m_fence = re.search(r"```(?:json)?\s*\n(.*?)```", cleaned, re.DOTALL | re.IGNORECASE)
    if m_fence:
        cleaned = m_fence.group(1).strip()

    start = cleaned.find("{")
    if start == -1:
        return cleaned

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
    """Local JSON sanitizer tolerant of common small-LLM formatting mistakes."""
    candidate = strip_reasoning_and_extract_json(raw_text)
    candidate = candidate.replace("\u201c", '"').replace("\u201d", '"').replace("\u2018", "'").replace("\u2019", "'")
    candidate = re.sub(r",\s*([}\]])", r"\1", candidate)
    candidate = re.sub(r"(?<=[:\[,\s])\bTrue\b(?=\s*[,}\]])", "true", candidate)
    candidate = re.sub(r"(?<=[:\[,\s])\bFalse\b(?=\s*[,}\]])", "false", candidate)
    candidate = re.sub(r"(?<=[:\[,\s])\bNone\b(?=\s*[,}\]])", "null", candidate)

    data = json.loads(candidate)
    if not isinstance(data, dict):
        raise ValueError("JSON root must be an object.")

    # Normalize language to Literal["en", "es"]
    raw_lang = str(data.get("language") or "en").strip().lower()
    data["language"] = "es" if raw_lang.startswith(("es", "span")) else "en"

    # Normalize top-level aliases
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

    for edge in data.get("edges") or []:
        if isinstance(edge, dict):
            if "source" not in edge and "from" in edge:
                edge["source"] = edge.pop("from")
            if "target" not in edge and "to" in edge:
                edge["target"] = edge.pop("to")
            if "is_loop" not in edge and "is_rework_loop" in edge:
                edge["is_loop"] = edge.pop("is_rework_loop")

    for node in data.get("nodes") or []:
        if isinstance(node, dict):
            nt = str(node.get("node_type", "task")).strip().lower()
            if nt == "end":
                lbl = str(node.get("label", "")).lower()
                node["node_type"] = (
                    "end_reject"
                    if any(w in lbl for w in ("reject", "cancel", "deny", "fail", "abort", "declin", "archiv", "rechaz", "deneg"))
                    else "end_success"
                )
            elif nt in NODE_TYPE_ALIASES:
                node["node_type"] = NODE_TYPE_ALIASES[nt]
            elif nt not in VALID_NODE_TYPES:
                node["node_type"] = "task"

            if "is_automated" not in node:
                if "automation_level" in node:
                    node["is_automated"] = str(node.get("automation_level")).lower() == "automated"
                elif node["node_type"] == "system":
                    node["is_automated"] = True

            if "estimated_duration_min" in node:
                node["estimated_duration_min"] = _coerce_duration_minutes(node["estimated_duration_min"])

    for lane in data.get("lanes") or []:
        if isinstance(lane, dict):
            if "kind" not in lane and "role_type" in lane:
                rt = str(lane.pop("role_type")).lower()
                lane["kind"] = "human" if rt in ("customer", "management") else (rt if rt in ("system", "department", "external") else "department")
            elif str(lane.get("kind", "")).lower() not in ("human", "system", "department", "external"):
                lane["kind"] = "department"

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
    """Primary ALVEA v3.0 orchestrator: generation, validation, NetworkX analytics, and reporting."""

    def __init__(self) -> None:
        self.nlp_engine = LocalBPAEngine()
        self.mermaid_gen = MermaidGenerator()
        self.mermaid_val = MermaidValidator()
        self.mermaid_parser = MermaidParser()
        self.analyzer = GraphAnalyzer()
        self.report_builder = ReportBuilder()
        self.sop_generator = SOPGenerator()
        self.swimlane_svg = SwimlaneSVGRenderer()

    def build_from_graph(
        self,
        *,
        graph: ProcessGraph,
        direction: Direction = Direction.LR,
        highlight_critical: bool = False,
        align_ends_right: bool = True,
    ) -> PipelineOutcome:
        """Compiles a structured ProcessGraph from the Visual Builder directly into BPMN SVG + Mermaid + NetworkX + SOP."""
        t0 = time.perf_counter()
        graph.direction = direction
        return self._finalize(
            graph=graph,
            direction=direction,
            highlight_critical=highlight_critical,
            align_ends_right=align_ends_right,
            provider_id="visual_builder",
            provider_name="Visual Builder + Python Engine",
            model_id="structured-bpmn-v4",
            stage="structured_graph",
            fallback_notice=None,
            started_at=t0,
        )

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
        custom_protocol: str | None = None,
        custom_auth_header: str | None = None,
        custom_auth_prefix: str | None = None,
        allow_native_fallback: bool = True,
    ) -> PipelineOutcome:
        t0 = time.perf_counter()
        provider = get_provider(provider_id)
        if provider is None:
            raise ProviderCallError(f"Unknown provider: '{provider_id}'.", status_code=400)

        chosen_model = (model_id or provider.default_model or "alvea-bpa-v3").strip()
        stage = "native_python"
        fallback_notice: str | None = None

        if provider.protocol == "native":
            graph = self.nlp_engine.parse(text, direction=direction, title=title)
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
                    custom_protocol=custom_protocol,
                    custom_auth_header=custom_auth_header,
                    custom_auth_prefix=custom_auth_prefix,
                )
            except (ProviderCallError, SSRFBlockedError) as exc:
                # For Google Gemini, if the chosen model hits 429/503/404 (e.g. zero-quota preview or peak load),
                # automatically try one high-availability Flash/Flash-Lite fallback model before giving up on Gemini.
                recovered = False
                if (
                    provider.id == "gemini"
                    and isinstance(exc, ProviderCallError)
                    and exc.status_code in (429, 503, 404)
                ):
                    for alt_model in ("gemini-2.5-flash", "gemini-2.5-flash-lite", "gemini-3.1-flash-lite"):
                        if alt_model == chosen_model:
                            continue
                        try:
                            graph, stage = self._run_llm_with_repair(
                                text=text,
                                provider=provider,
                                model_id=alt_model,
                                direction=direction,
                                title=title,
                                api_key=api_key,
                                base_url=base_url,
                                custom_protocol=custom_protocol,
                                custom_auth_header=custom_auth_header,
                                custom_auth_prefix=custom_auth_prefix,
                            )
                            fallback_notice = (
                                f"Switched to {alt_model} because '{chosen_model}' returned HTTP {exc.status_code}."
                            )
                            chosen_model = alt_model
                            recovered = True
                            break
                        except ProviderCallError as alt_exc:
                            if alt_exc.status_code == 401:
                                raise
                            continue

                if not recovered:
                    if not allow_native_fallback or isinstance(exc, SSRFBlockedError) or getattr(exc, "status_code", 500) == 401:
                        raise
                    graph = self.nlp_engine.parse(text, direction=direction, title=title)
                    stage = "native_fallback"
                    fallback_notice = f"Automatic fallback to Native Python Engine ({exc})"

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
        sop = self.sop_generator.generate(graph, analytics)
        svg_markup = self.swimlane_svg.render(
            graph,
            analytics=analytics,
            direction=target_dir,
            highlight_critical=highlight_critical,
            align_ends_right=True,
        )

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
            swimlane_svg=svg_markup,
            mermaid=final_mermaid,
            analytics=analytics.model_dump(),
            report=report.model_dump(),
            sop=sop.model_dump(),
            validation=val.model_dump(),
            meta={
                "provider": "mermaid_editor",
                "provider_name": "Mermaid Editor + NetworkX",
                "model": "deterministic-parser",
                "stage": "repaired" if val.repairs_applied else "validated",
                "elapsed_ms": elapsed_ms,
                "fallback_notice": None,
            },
        )

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
        custom_protocol: str | None = None,
        custom_auth_header: str | None = None,
        custom_auth_prefix: str | None = None,
    ) -> tuple[ProcessGraph, str]:
        model_spec = get_model_spec(provider, model_id)
        use_compact = bool(
            (model_spec and model_spec.compact_prompt)
            or re.search(r"[:\-_/](?:1|2|3|4|7|8|e4)b\b", model_id, re.I)
        )
        system_prompt = SYSTEM_PROMPT_COMPACT if use_compact else SYSTEM_PROMPT_FULL
        user_prompt = build_user_prompt(text, direction=direction.value)
        schema = ProcessGraph.model_json_schema()

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
                    custom_protocol=custom_protocol,
                    custom_auth_header=custom_auth_header,
                    custom_auth_prefix=custom_auth_prefix,
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

        try:
            parsed_dict = repair_and_parse_json_dict(raw_output)
            graph = ProcessGraph.model_validate(parsed_dict)
            if len(graph.nodes) >= 2 and len(graph.edges) == 0:
                raise ValueError("The graph contains disconnected nodes with no valid edges.")
            stage = "strict_json" if used_mode == "json_schema" else "sanitized_json"
            return graph, stage
        except (json.JSONDecodeError, ValueError, ValidationError) as parse_err:
            if mermaid_hint_re.search(cleaned_raw):
                graph = self.mermaid_parser.parse(cleaned_raw, title=title)
                return graph, "mermaid_fallback"

            repair_mode: StructuredMode = "json_object" if used_mode == "json_schema" else used_mode
            repaired_raw = ""
            try:
                repair_req = (
                    f"Validation error:\n{str(parse_err)[:500]}\n\n"
                    f"Original JSON to fix:\n{cleaned_raw[:4000]}"
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
                    custom_protocol=custom_protocol,
                    custom_auth_header=custom_auth_header,
                    custom_auth_prefix=custom_auth_prefix,
                    temperature=0.0,
                )
                parsed_dict = repair_and_parse_json_dict(repaired_raw)
                graph = ProcessGraph.model_validate(parsed_dict)
                if len(graph.nodes) >= 2 and len(graph.edges) == 0:
                    raise ValueError("The repaired graph contains no valid edges.")
                return graph, "llm_self_repaired"
            except Exception:
                cleaned_repaired = THINK_BLOCK_RE.sub("", repaired_raw).strip()
                if cleaned_repaired and mermaid_hint_re.search(cleaned_repaired):
                    return self.mermaid_parser.parse(cleaned_repaired, title=title), "mermaid_fallback"
                if mermaid_hint_re.search(cleaned_raw):
                    return self.mermaid_parser.parse(cleaned_raw, title=title), "mermaid_fallback"
                raise ProviderCallError(
                    f"Model '{model_id}' returned an invalid structure after self-repair.",
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
        align_ends_right: bool = True,
    ) -> PipelineOutcome:
        analytics = self.analyzer.analyze(graph)
        report = self.report_builder.build(graph, analytics)
        sop = self.sop_generator.generate(graph, analytics)
        svg_markup = self.swimlane_svg.render(
            graph,
            analytics=analytics,
            direction=direction,
            highlight_critical=highlight_critical,
            align_ends_right=align_ends_right,
        )
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
            swimlane_svg=svg_markup,
            mermaid=mermaid_code,
            analytics=analytics.model_dump(),
            report=report.model_dump(),
            sop=sop.model_dump(),
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
