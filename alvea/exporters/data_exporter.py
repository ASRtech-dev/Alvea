"""Exportadores e importadores de especificación de proceso en YAML y JSON."""

from __future__ import annotations

import json
from typing import Any

import yaml

from alvea.models import ExecutiveReport, GraphAnalytics, ProcessGraph


def build_canonical_bundle(
    *,
    graph: ProcessGraph,
    analytics: GraphAnalytics,
    report: ExecutiveReport,
    mermaid_code: str,
) -> dict[str, Any]:
    return {
        "schema_version": "2.0",
        "tool": "ALVEA Process Architecture Studio",
        "process_graph": graph.model_dump(mode="json"),
        "analytics": analytics.model_dump(mode="json"),
        "executive_report": report.model_dump(mode="json"),
        "mermaid": mermaid_code,
    }


def export_yaml_bytes(
    *,
    graph: ProcessGraph,
    analytics: GraphAnalytics,
    report: ExecutiveReport,
    mermaid_code: str,
) -> bytes:
    bundle = build_canonical_bundle(
        graph=graph,
        analytics=analytics,
        report=report,
        mermaid_code=mermaid_code,
    )
    text = yaml.safe_dump(bundle, allow_unicode=True, sort_keys=False, width=100)
    return text.encode("utf-8")


def export_json_bytes(
    *,
    graph: ProcessGraph,
    analytics: GraphAnalytics,
    report: ExecutiveReport,
    mermaid_code: str,
) -> bytes:
    bundle = build_canonical_bundle(
        graph=graph,
        analytics=analytics,
        report=report,
        mermaid_code=mermaid_code,
    )
    return json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")


def import_yaml_to_graph(raw_yaml: str) -> ProcessGraph:
    """Parsea de forma segura (safe_load) un archivo YAML de ALVEA y valida con Pydantic."""
    loaded = yaml.safe_load(raw_yaml)
    if not isinstance(loaded, dict):
        raise ValueError("El archivo YAML debe contener un objeto raíz válido.")

    graph_data = loaded.get("process_graph") if "process_graph" in loaded else loaded
    if not isinstance(graph_data, dict):
        raise ValueError("No se encontró una sección 'process_graph' válida en el YAML.")

    return ProcessGraph.model_validate(graph_data)
