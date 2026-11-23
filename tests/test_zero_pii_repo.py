"""Auditoría automática Zero-PII, Zero-Secrets y Zero-Loose-Mermaid sobre el repositorio."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}
SKIP_REL_PATHS = {
    "static/vendor/mermaid.min.js",
    "tests/test_zero_pii_repo.py",
    "tests/test_ai_pipeline.py",
    "tests/test_security_paths_and_api.py",
    "tests/test_mermaid_engine.py",
}

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Ruta absoluta Windows C:\\Users\\", re.compile(r"(?i)[a-z]:\\users\\")),
    ("Ruta absoluta macOS/Linux /Users/ o /home/", re.compile(r"(?:/Users/|/home/)[A-Za-z0-9._\-]+")),
    ("Google API Key real", re.compile(r"AIza[0-9A-Za-z_\-]{20,}")),
    ("OpenAI/Anthropic/OpenRouter key real", re.compile(r"sk-(?:or-v1-|ant-)?[0-9A-Za-z_\-]{20,}")),
    ("GitHub PAT real", re.compile(r"(?:ghp|github_pat)_[0-9A-Za-z_\-]{20,}")),
    ("Clave privada embebida", re.compile(r"BEGIN (?:RSA|OPENSSH|EC) PRIVATE KEY")),
    ("Mermaid securityLevel loose", re.compile(r'securityLevel\s*:\s*["\']loose["\']')),
    ("Uso inseguro de document.write", re.compile(r"\bdocument\.write\s*\(")),
)


class TestZeroPIIRepository(unittest.TestCase):
    def test_repository_contains_no_pii_secrets_or_insecure_mermaid(self) -> None:
        violations: list[str] = []
        for path in REPO_ROOT.rglob("*"):
            if not path.is_file():
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in SKIP_REL_PATHS:
                continue
            if path.suffix.lower() in {".png", ".jpg", ".ico", ".pdf", ".woff2", ".pyc"}:
                continue

            try:
                content = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue

            for label, pat in FORBIDDEN_PATTERNS:
                if pat.search(content):
                    violations.append(f"{rel}: detectado '{label}'")

        self.assertEqual(violations, [], f"Violaciones Zero-PII/Seguridad encontradas:\n" + "\n".join(violations))


if __name__ == "__main__":
    unittest.main()
