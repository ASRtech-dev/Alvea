"""Redacción automática de credenciales y secretos en logs y mensajes de error."""

from __future__ import annotations

import logging
import re

_SECRET_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"AIza[0-9A-Za-z_\-]{16,}"), "[REDACTED_GOOGLE_KEY]"),
    (re.compile(r"sk-or-v1-[0-9A-Za-z_\-]{16,}"), "[REDACTED_OPENROUTER_KEY]"),
    (re.compile(r"sk-ant-[0-9A-Za-z_\-]{16,}"), "[REDACTED_ANTHROPIC_KEY]"),
    (re.compile(r"sk-[0-9A-Za-z_\-]{16,}"), "[REDACTED_API_KEY]"),
    (re.compile(r"gsk_[0-9A-Za-z_\-]{16,}"), "[REDACTED_GROQ_KEY]"),
    (re.compile(r"csk-[0-9A-Za-z_\-]{16,}"), "[REDACTED_CEREBRAS_KEY]"),
    (re.compile(r"(?:ghp|gho|github_pat)_[0-9A-Za-z_\-]{16,}"), "[REDACTED_GITHUB_TOKEN]"),
    (re.compile(r"(?i)(Bearer\s+)[^\s\"',;]+"), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(?i)([?&](?:key|api_key|token)=)[^&\s\"']+"), r"\1[REDACTED]"),
)


def redact_secrets(text: str) -> str:
    """Enmascara cualquier patrón de API key o token en cadenas de log o error."""
    result = str(text)
    for pattern, replacement in _SECRET_PATTERNS:
        result = pattern.sub(replacement, result)
    return result


class SecretRedactionFilter(logging.Filter):
    """Filtro de logging que enmascara secretos antes de emitir registros."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {
                    k: redact_secrets(v) if isinstance(v, str) else v
                    for k, v in record.args.items()
                }
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    redact_secrets(a) if isinstance(a, str) else a
                    for a in record.args
                )
        return True
