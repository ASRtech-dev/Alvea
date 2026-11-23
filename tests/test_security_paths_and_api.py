"""Pruebas de Path Traversal, cabeceras de seguridad, límites 413, Zero-Key-Leak y Exportadores."""

from __future__ import annotations

import logging
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

from alvea.ai.providers import ProviderCallError
from alvea.security.paths import safe_resolve_static
from alvea.server.app import create_server


class TestSecurityPathsAndHTTPAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.server = create_server(host="127.0.0.1", port=0)
        cls.port = cls.server.server_address[1]
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_security_headers_present_on_static_and_api(self) -> None:
        with httpx.Client(base_url=self.base_url) as client:
            r_root = client.get("/")
            self.assertEqual(r_root.status_code, 200)
            self.assertIn("script-src 'self'", r_root.headers.get("content-security-policy", ""))
            self.assertEqual(r_root.headers.get("x-content-type-options"), "nosniff")
            self.assertEqual(r_root.headers.get("x-frame-options"), "DENY")
            self.assertEqual(r_root.headers.get("referrer-policy"), "no-referrer")

            r_api = client.get("/api/v1/health")
            self.assertEqual(r_api.status_code, 200)
            self.assertIn("no-store", r_api.headers.get("cache-control", ""))

    def test_path_traversal_vectors_are_blocked(self) -> None:
        vectors = [
            "/../pyproject.toml",
            "/..%2fpyproject.toml",
            "/%2e%2e/README.md",
            "/..%5cREADME.md",
            "/.env",
            "/index.html%00.png",
        ]
        with httpx.Client(base_url=self.base_url) as client:
            for vec in vectors:
                with self.subTest(vector=vec):
                    resp = client.get(vec)
                    self.assertIn(resp.status_code, (400, 403, 404))

    def test_safe_resolve_blocks_sibling_prefix_and_hidden(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "static"
            sibling = Path(tmp) / "static_secret"
            root.mkdir()
            sibling.mkdir()
            (root / "ok.html").write_text("<h1>ok</h1>", encoding="utf-8")
            (sibling / "leak.html").write_text("secret", encoding="utf-8")

            self.assertEqual(safe_resolve_static("/ok.html", static_root=root).name, "ok.html")
            with self.assertRaises(PermissionError):
                safe_resolve_static("/../static_secret/leak.html", static_root=root)
            with self.assertRaises(PermissionError):
                safe_resolve_static("/.secret", static_root=root)

    def test_payload_too_large_returns_413(self) -> None:
        oversized = {"text": "A" * 70_000, "provider": "native_python"}
        with httpx.Client(base_url=self.base_url) as client:
            resp = client.post("/api/v1/generate", json=oversized)
            self.assertEqual(resp.status_code, 413)

    def test_zero_key_leak_in_errors_and_logs(self) -> None:
        sentinel = "AIzaSySENTINEL_NEVER_LEAK_1234567890"
        log_records: list[str] = []

        class ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                log_records.append(self.format(record))

        handler = ListHandler()
        logger = logging.getLogger("alvea.server")
        logger.addHandler(handler)
        try:
            with patch(
                "alvea.ai.pipeline.call_llm_provider",
                side_effect=ProviderCallError(f"Error remoto con clave {sentinel}", status_code=401),
            ):
                with httpx.Client(base_url=self.base_url) as client:
                    resp = client.post(
                        "/api/v1/generate",
                        headers={"X-API-Key": sentinel},
                        json={
                            "text": "Un cliente realiza una solicitud y el sistema valida.",
                            "provider": "gemini",
                            "model": "gemini-3.8-flash",
                            "allow_native_fallback": False,
                        },
                    )
                    self.assertEqual(resp.status_code, 401)
                    self.assertNotIn(sentinel, resp.text)
            for rec in log_records:
                self.assertNotIn(sentinel, rec)
        finally:
            logger.removeHandler(handler)

    def test_generate_export_pdf_yaml_json_and_import_yaml(self) -> None:
        with httpx.Client(base_url=self.base_url) as client:
            gen = client.post(
                "/api/v1/generate",
                json={
                    "text": "Cliente registra reclamo. Soporte valida el caso. Si es procedente, Finanzas reembolsa el dinero.",
                    "provider": "native_python",
                    "direction": "LR",
                },
            )
            self.assertEqual(gen.status_code, 200)
            payload = gen.json()
            mermaid = payload["mermaid"]
            self.assertIn("graph LR", mermaid)
            self.assertGreaterEqual(payload["analytics"]["node_count"], 3)

            # Export PDF (ReportLab)
            pdf_resp = client.post("/api/v1/export/pdf", json={"mermaid": mermaid, "title": "Prueba PDF"})
            self.assertEqual(pdf_resp.status_code, 200)
            self.assertEqual(pdf_resp.headers.get("content-type"), "application/pdf")
            self.assertTrue(pdf_resp.content.startswith(b"%PDF-"))

            # Export YAML + Re-import YAML
            yaml_resp = client.post("/api/v1/export/yaml", json={"mermaid": mermaid, "title": "Prueba YAML"})
            self.assertEqual(yaml_resp.status_code, 200)
            imp_resp = client.post("/api/v1/import/yaml", json={"yaml_content": yaml_resp.text})
            self.assertEqual(imp_resp.status_code, 200)
            self.assertIn("mermaid", imp_resp.json())

            # Export JSON
            json_resp = client.post("/api/v1/export/json", json={"mermaid": mermaid, "title": "Prueba JSON"})
            self.assertEqual(json_resp.status_code, 200)
            self.assertIn("process_graph", json_resp.json())

            # Auto-repair=False debe sanitizar XSS igualmente
            xss_resp = client.post(
                "/api/v1/mermaid/validate",
                json={
                    "code": 'graph LR\nA["Inicio"] --> B["Fin"]\nclick A "javascript:alert(1)"',
                    "auto_repair": False,
                },
            )
            self.assertEqual(xss_resp.status_code, 200)
            self.assertNotIn("click A", xss_resp.json()["mermaid"])


if __name__ == "__main__":
    unittest.main()
