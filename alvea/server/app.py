"""Hardened multithreaded HTTP server for ALVEA v3.0 (English Default, Zero Presets)."""

from __future__ import annotations

import json
import logging
import mimetypes
import sys
import threading
import time
import webbrowser
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic import ValidationError

from alvea import __app_name__, __version__
from alvea.ai.catalog import catalog_as_json
from alvea.ai.pipeline import ProcessPipeline
from alvea.ai.prompts import SYSTEM_PROMPT_COMPACT, SYSTEM_PROMPT_FULL
from alvea.ai.providers import ProviderCallError, discover_local_models, test_provider_connection
from alvea.config import SETTINGS, STATIC_ROOT
from alvea.engine.sop import render_sop_markdown
from alvea.exporters.data_exporter import (
    export_json_bytes,
    export_yaml_bytes,
    import_yaml_to_graph,
)
from alvea.exporters.pdf_exporter import export_executive_pdf, export_sop_pdf
from alvea.models import (
    ExportRequest,
    GenerateRequest,
    ImportYamlRequest,
    ProcessGraph,
    StructuredWorkflowRequest,
    TestProviderRequest,
    ValidateMermaidRequest,
)
from alvea.security import (
    SSRFBlockedError,
    SecretRedactionFilter,
    redact_secrets,
    safe_resolve_static,
)

LOGGER = logging.getLogger("alvea.server")
LOGGER.addFilter(SecretRedactionFilter())

CSP_HEADER = (
    "default-src 'self'; "
    "script-src 'self'; "
    "style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; "
    "font-src 'self'; "
    "connect-src 'self'; "
    "object-src 'none'; "
    "base-uri 'self'; "
    "frame-ancestors 'none'; "
    "form-action 'self'"
)

MIME_OVERRIDES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".txt": "text/plain; charset=utf-8",
}


class InMemoryRateLimiter:
    """Lightweight per-IP in-memory rate limiter for generation and PDF endpoints."""

    def __init__(self, max_per_min: int = 40) -> None:
        self.max_per_min = max_per_min
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, client_ip: str) -> bool:
        now = time.monotonic()
        cutoff = now - 60.0
        with self._lock:
            q = self._hits[client_ip]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= self.max_per_min:
                return False
            q.append(now)
            return True


class AlveaHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows, SO_REUSEADDR allows two processes to bind the same port simultaneously
    allow_reuse_address = sys.platform != "win32"

    def __init__(self, server_address: tuple[str, int], *, static_root: Path | None = None) -> None:
        self.static_root = (static_root or STATIC_ROOT).resolve()
        self.pipeline = ProcessPipeline()
        self.rate_limiter = InMemoryRateLimiter(SETTINGS.rate_limit_per_min)
        super().__init__(server_address, AlveaRequestHandler)


class MissingContentLengthError(ValueError):
    """Raised when a POST request omits Content-Length (HTTP 411)."""


class AlveaRequestHandler(BaseHTTPRequestHandler):
    server: AlveaHTTPServer  # type: ignore[assignment]
    protocol_version = "HTTP/1.1"
    timeout = 15.0  # Anti-Slowloris socket timeout on HTTP/1.1 keep-alive

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        msg = format % args if args else format
        LOGGER.info("%s - %s", self.client_address[0], redact_secrets(msg))

    def _add_security_headers(self, *, is_api: bool) -> None:
        self.send_header("Content-Security-Policy", CSP_HEADER)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()")
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        if is_api:
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")

    def _send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._add_security_headers(is_api=True)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_bytes(
        self,
        status: int,
        body: bytes,
        *,
        content_type: str,
        is_api: bool = False,
        download_filename: str | None = None,
    ) -> None:
        self.send_response(status)
        self._add_security_headers(is_api=is_api)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if download_filename:
            self.send_header("Content-Disposition", f'attachment; filename="{download_filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self, max_bytes: int) -> dict[str, Any]:
        if self.headers.get("Transfer-Encoding"):
            raise MissingContentLengthError("Chunked Transfer-Encoding is not supported; send Content-Length.")
        cl_header = self.headers.get("Content-Length")
        if cl_header is None:
            raise MissingContentLengthError("Content-Length header is required.")
        try:
            content_length = int(cl_header)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc
        if content_length < 0:
            raise ValueError("Negative Content-Length header.")
        if content_length > max_bytes:
            raise OverflowError(f"Payload exceeds maximum allowed size ({max_bytes // 1024} KB).")
        raw = self.rfile.read(content_length)

        if not raw:
            return {}
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body is not valid UTF-8 JSON.") from exc
        if not isinstance(parsed, dict):
            raise ValueError("JSON body must be an object.")
        return parsed

    # ─── GET ────────────────────────────────────────────────────────────────────

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        if path == "/api/v1/health":
            self._send_json(
                HTTPStatus.OK,
                {
                    "status": "ok",
                    "app": __app_name__,
                    "version": __version__,
                    "engines": {
                        "native_python": True,
                        "networkx": True,
                        "pdf_reportlab": True,
                        "yaml": True,
                    },
                },
            )
            return

        if path == "/api/v1/providers":
            self._send_json(HTTPStatus.OK, {"providers": catalog_as_json()})
            return

        if path.startswith("/api/v1/providers/") and path.endswith("/models"):
            parts = path.strip("/").split("/")
            if len(parts) == 5:
                provider_id = parts[3]
                custom_url = self.headers.get("X-Provider-Base-Url")
                result = discover_local_models(provider_id, custom_base_url=custom_url)
                self._send_json(HTTPStatus.OK, result)
                return

        if path == "/api/v1/prompt":
            self._send_json(
                HTTPStatus.OK,
                {
                    "system_prompt_full": SYSTEM_PROMPT_FULL,
                    "system_prompt_compact": SYSTEM_PROMPT_COMPACT,
                },
            )
            return

        if path.startswith("/api/"):
            self._send_json(HTTPStatus.NOT_FOUND, {"error": "API endpoint not found."})
            return

        self._serve_static(path)

    def _serve_static(self, raw_path: str) -> None:
        try:
            resolved = safe_resolve_static(raw_path, static_root=self.server.static_root)
        except PermissionError:
            self._send_bytes(HTTPStatus.FORBIDDEN, b"403 Access Denied", content_type="text/plain; charset=utf-8")
            return
        except FileNotFoundError:
            self._send_bytes(HTTPStatus.NOT_FOUND, b"404 Not Found", content_type="text/plain; charset=utf-8")
            return

        ext = resolved.suffix.lower()
        content_type = MIME_OVERRIDES.get(ext) or mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
        data = resolved.read_bytes()
        self._send_bytes(HTTPStatus.OK, data, content_type=content_type, is_api=False)

    # ─── POST ───────────────────────────────────────────────────────────────────

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path

        try:
            if path == "/api/v1/providers/test":
                if not self.server.rate_limiter.allow(self.client_address[0]):
                    self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Too many connection test requests."})
                    return
                body = self._read_json_body(SETTINGS.max_analyze_body_bytes)
                header_key = self.headers.get("X-API-Key")
                if header_key and "api_key" not in body:
                    body["api_key"] = header_key
                req = TestProviderRequest.model_validate(body)
                result = test_provider_connection(
                    provider_id=req.provider,
                    model_id=req.model,
                    api_key=req.api_key.get_secret_value() if req.api_key else None,
                    custom_base_url=req.base_url,
                    custom_protocol=req.custom_protocol,
                    custom_auth_header=req.custom_auth_header,
                    custom_auth_prefix=req.custom_auth_prefix,
                )
                self._send_json(HTTPStatus.OK, result)
                return

            if path == "/api/v1/graph/build":
                if not self.server.rate_limiter.allow(self.client_address[0]):
                    self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Too many requests. Please retry shortly."})
                    return
                body = self._read_json_body(SETTINGS.max_analyze_body_bytes)
                req = StructuredWorkflowRequest.model_validate(body)
                graph = ProcessGraph(
                    title=req.title,
                    objective=req.objective,
                    direction=req.direction,
                    lanes=req.lanes,
                    nodes=req.nodes,
                    edges=req.edges,
                )
                outcome = self.server.pipeline.build_from_graph(
                    graph=graph,
                    direction=req.direction,
                    highlight_critical=req.highlight_critical,
                    align_ends_right=req.align_ends_right,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "graph": outcome.graph.model_dump(mode="json"),
                        "swimlane_svg": outcome.swimlane_svg,
                        "mermaid": outcome.mermaid,
                        "analytics": outcome.analytics,
                        "report": outcome.report,
                        "sop": outcome.sop,
                        "validation": outcome.validation,
                        "meta": outcome.meta,
                    },
                )
                return

            if path == "/api/v1/generate":
                if not self.server.rate_limiter.allow(self.client_address[0]):
                    self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Too many requests. Please retry shortly."})
                    return
                body = self._read_json_body(SETTINGS.max_analyze_body_bytes)
                header_key = self.headers.get("X-API-Key")
                if header_key and "api_key" not in body:
                    body["api_key"] = header_key
                req = GenerateRequest.model_validate(body)
                outcome = self.server.pipeline.generate(
                    text=req.text,
                    provider_id=req.provider,
                    model_id=req.model,
                    direction=req.direction,
                    highlight_critical=req.highlight_critical,
                    title=req.title,
                    api_key=req.api_key.get_secret_value() if req.api_key else None,
                    base_url=req.base_url,
                    custom_protocol=req.custom_protocol,
                    custom_auth_header=req.custom_auth_header,
                    custom_auth_prefix=req.custom_auth_prefix,
                    allow_native_fallback=req.allow_native_fallback,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "graph": outcome.graph.model_dump(mode="json"),
                        "swimlane_svg": outcome.swimlane_svg,
                        "mermaid": outcome.mermaid,
                        "analytics": outcome.analytics,
                        "report": outcome.report,
                        "sop": outcome.sop,
                        "validation": outcome.validation,
                        "meta": outcome.meta,
                    },
                )
                return

            if path == "/api/v1/mermaid/validate":
                body = self._read_json_body(SETTINGS.max_analyze_body_bytes)
                req = ValidateMermaidRequest.model_validate(body)
                outcome = self.server.pipeline.analyze_mermaid(
                    code=req.code,
                    direction=req.direction,
                    highlight_critical=req.highlight_critical,
                    auto_repair=req.auto_repair,
                    title=req.title,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "graph": outcome.graph.model_dump(mode="json"),
                        "swimlane_svg": outcome.swimlane_svg,
                        "mermaid": outcome.mermaid,
                        "analytics": outcome.analytics,
                        "report": outcome.report,
                        "sop": outcome.sop,
                        "validation": outcome.validation,
                        "meta": outcome.meta,
                    },
                )
                return

            if path in ("/api/v1/export/sop/pdf", "/api/v1/export/sop/markdown", "/api/v1/export/sop/md"):
                if path.endswith("/pdf") and not self.server.rate_limiter.allow(self.client_address[0]):
                    self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Too many SOP export requests."})
                    return
                limit = SETTINGS.max_body_bytes if path.endswith("/pdf") else SETTINGS.max_analyze_body_bytes
                body = self._read_json_body(limit)
                req = ExportRequest.model_validate(body)
                outcome = self._resolve_export_outcome(req)
                analytics_obj = self.server.pipeline.analyzer.analyze(outcome.graph)
                sop_obj = self.server.pipeline.sop_generator.generate(outcome.graph, analytics_obj)

                if path.endswith("/pdf"):
                    sop_pdf = export_sop_pdf(
                        sop=sop_obj,
                        graph=outcome.graph,
                        diagram_png_base64=req.diagram_png_base64,
                    )
                    self._send_bytes(
                        HTTPStatus.OK,
                        sop_pdf,
                        content_type="application/pdf",
                        is_api=True,
                        download_filename="alvea_sop_document.pdf",
                    )
                    return

                sop_md = render_sop_markdown(sop_obj).encode("utf-8")
                self._send_bytes(
                    HTTPStatus.OK,
                    sop_md,
                    content_type="text/markdown; charset=utf-8",
                    is_api=True,
                    download_filename="alvea_sop_document.md",
                )
                return

            if path in ("/api/v1/export/pdf", "/api/v1/export/yaml", "/api/v1/export/json"):
                if path.endswith("/pdf") and not self.server.rate_limiter.allow(self.client_address[0]):
                    self._send_json(HTTPStatus.TOO_MANY_REQUESTS, {"error": "Too many PDF export requests."})
                    return
                limit = SETTINGS.max_body_bytes if path.endswith("/pdf") else SETTINGS.max_analyze_body_bytes
                body = self._read_json_body(limit)
                req = ExportRequest.model_validate(body)
                outcome = self._resolve_export_outcome(req)

                analytics_obj = self.server.pipeline.analyzer.analyze(outcome.graph)
                report_obj = self.server.pipeline.report_builder.build(outcome.graph, analytics_obj)

                if path.endswith("/pdf"):
                    pdf_bytes = export_executive_pdf(
                        graph=outcome.graph,
                        analytics=analytics_obj,
                        report=report_obj,
                        mermaid_code=outcome.mermaid,
                        diagram_png_base64=req.diagram_png_base64,
                    )
                    self._send_bytes(
                        HTTPStatus.OK,
                        pdf_bytes,
                        content_type="application/pdf",
                        is_api=True,
                        download_filename="alvea_executive_report.pdf",
                    )
                    return

                if path.endswith("/yaml"):
                    yaml_bytes = export_yaml_bytes(
                        graph=outcome.graph,
                        analytics=analytics_obj,
                        report=report_obj,
                        mermaid_code=outcome.mermaid,
                    )
                    self._send_bytes(
                        HTTPStatus.OK,
                        yaml_bytes,
                        content_type="application/x-yaml; charset=utf-8",
                        is_api=True,
                        download_filename="alvea_workflow.yaml",
                    )
                    return

                json_bytes = export_json_bytes(
                    graph=outcome.graph,
                    analytics=analytics_obj,
                    report=report_obj,
                    mermaid_code=outcome.mermaid,
                )
                self._send_bytes(
                    HTTPStatus.OK,
                    json_bytes,
                    content_type="application/json; charset=utf-8",
                    is_api=True,
                    download_filename="alvea_workflow.json",
                )
                return

            if path == "/api/v1/import/yaml":
                body = self._read_json_body(SETTINGS.max_analyze_body_bytes)
                req = ImportYamlRequest.model_validate(body)
                graph = import_yaml_to_graph(req.yaml_content)
                analytics = self.server.pipeline.analyzer.analyze(graph)
                report = self.server.pipeline.report_builder.build(graph, analytics)
                sop = self.server.pipeline.sop_generator.generate(graph, analytics)
                mermaid = self.server.pipeline.mermaid_gen.render(graph)
                svg_markup = self.server.pipeline.swimlane_svg.render(
                    graph,
                    analytics=analytics,
                    direction=graph.direction,
                    highlight_critical=False,
                    align_ends_right=True,
                )
                self._send_json(
                    HTTPStatus.OK,
                    {
                        "graph": graph.model_dump(mode="json"),
                        "swimlane_svg": svg_markup,
                        "mermaid": mermaid,
                        "analytics": analytics.model_dump(mode="json"),
                        "report": report.model_dump(mode="json"),
                        "sop": sop.model_dump(mode="json"),
                    },
                )
                return

            self._send_json(HTTPStatus.NOT_FOUND, {"error": "POST endpoint not found."})

        except MissingContentLengthError as exc:
            self.close_connection = True
            self._send_json(HTTPStatus.LENGTH_REQUIRED, {"error": str(exc)})
        except OverflowError as exc:
            self.close_connection = True
            self._send_json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": str(exc)})
        except SSRFBlockedError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": f"Blocked by security policy: {exc}"})
        except ProviderCallError as exc:
            self._send_json(exc.status_code, {"error": redact_secrets(str(exc))})
        except ValidationError as exc:
            safe_errors = [
                {"loc": ".".join(str(x) for x in e.get("loc", [])), "msg": e.get("msg", "Invalid")}
                for e in exc.errors()[:5]
            ]
            self._send_json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": "Invalid input payload.", "details": safe_errors})
        except ValueError as exc:
            self._send_json(HTTPStatus.BAD_REQUEST, {"error": redact_secrets(str(exc))})
        except Exception:
            LOGGER.exception("Internal error while handling %s", path)
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "Internal server error."})

    def _resolve_export_outcome(self, req: ExportRequest):
        if req.mermaid and req.mermaid.strip():
            return self.server.pipeline.analyze_mermaid(
                code=req.mermaid,
                direction=req.direction,
                title=req.title,
            )
        if req.text and req.text.strip():
            return self.server.pipeline.generate(
                text=req.text,
                provider_id="native_python",
                direction=req.direction,
                title=req.title,
            )
        raise ValueError("Provide either 'mermaid' or 'text' to export.")


def create_server(
    host: str | None = None,
    port: int | None = None,
    *,
    static_root: Path | None = None,
    auto_port: bool = False,
) -> AlveaHTTPServer:
    bind_host = host or SETTINGS.host
    bind_port = SETTINGS.port if port is None else port
    if bind_port < 0 or bind_port > 65535:
        raise ValueError("Port must be between 0 and 65535.")
    if not auto_port or bind_port == 0:
        return AlveaHTTPServer((bind_host, bind_port), static_root=static_root)

    last_err: OSError | None = None
    for candidate in range(bind_port, min(bind_port + 11, 65536)):
        try:
            return AlveaHTTPServer((bind_host, candidate), static_root=static_root)
        except OSError as exc:
            last_err = exc
    raise last_err or OSError(f"No free port available in range {bind_port}-{min(bind_port + 10, 65535)}.")


def run_server(
    host: str | None = None,
    port: int | None = None,
    *,
    open_browser: bool = False,
    auto_port: bool = True,
) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    for handler in logging.getLogger().handlers:
        handler.addFilter(SecretRedactionFilter())

    srv = create_server(host=host, port=port, auto_port=auto_port)
    actual_host, actual_port = srv.server_address
    browser_host = "127.0.0.1" if actual_host in ("0.0.0.0", "::", "") else actual_host
    url = f"http://{browser_host}:{actual_port}"

    print("\n========================================================")
    print(f"  {__app_name__} v{__version__} - Process Architecture Studio")
    print(f"  Local URL : {url}")
    print("  Engine    : Python + NetworkX + ReportLab + Multi-LLM")
    print("  Press Ctrl+C to stop the server.")
    print("========================================================\n")

    if open_browser:
        timer = threading.Timer(0.45, webbrowser.open, args=[url])
        timer.daemon = True
        timer.start()

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nALVEA server stopped cleanly.")
    finally:
        srv.server_close()
