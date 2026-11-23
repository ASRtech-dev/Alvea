"""Configuración centralizada y límites de seguridad de ALVEA."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

BASE_DIR: Path = Path(__file__).resolve().parent.parent
STATIC_ROOT: Path = (BASE_DIR / "static").resolve()


@dataclass(frozen=True, slots=True)
class Settings:
    host: str = os.getenv("ALVEA_HOST", "127.0.0.1")
    port: int = int(os.getenv("ALVEA_PORT", "8000"))
    max_body_bytes: int = 3 * 1024 * 1024  # 3 MB (permite PNG HD opcional en /export/pdf)
    max_analyze_body_bytes: int = 64 * 1024  # 64 KB estricto para /analyze y /mermaid/*
    max_description_chars: int = 15_000
    max_mermaid_chars: int = 50_000
    max_llm_response_bytes: int = 512 * 1024
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 60.0
    local_probe_timeout_s: float = 1.5
    rate_limit_per_min: int = 40
    allow_docker_host: bool = os.getenv("ALVEA_ALLOW_DOCKER_HOST", "false").lower() == "true"
    default_ollama_url: str = os.getenv("ALVEA_OLLAMA_URL", "http://127.0.0.1:11434")
    default_lmstudio_url: str = os.getenv("ALVEA_LMSTUDIO_URL", "http://127.0.0.1:1234/v1")


SETTINGS = Settings()
