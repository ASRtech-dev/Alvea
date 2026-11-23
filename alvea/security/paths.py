"""Resolución segura de archivos estáticos con protección anti Path Traversal y Symlinks."""

from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote

from alvea.config import STATIC_ROOT

ALLOWED_STATIC_EXTS: frozenset[str] = frozenset({
    ".html",
    ".css",
    ".js",
    ".svg",
    ".png",
    ".ico",
    ".json",
    ".woff2",
    ".txt",
})


def safe_resolve_static(raw_url_path: str, *, static_root: Path | None = None) -> Path:
    """Resuelve una ruta HTTP confinada estrictamente dentro de STATIC_ROOT.

    Lanza PermissionError ante intentos de traversal, extensiones prohibidas o symlinks externos,
    y FileNotFoundError si el archivo no existe.
    """
    root = (static_root or STATIC_ROOT).resolve()

    if not isinstance(raw_url_path, str):
        raise PermissionError("Ruta inválida.")

    # Rechazar nulos o backslashes antes y después de decodificar
    if "\x00" in raw_url_path or "\\" in raw_url_path:
        raise PermissionError("Caracteres prohibidos en la ruta.")

    # Detectar doble codificación de traversal (%252e)
    lowered_raw = raw_url_path.lower()
    if "%25" in lowered_raw or "%00" in lowered_raw or "%5c" in lowered_raw:
        raise PermissionError("Secuencia codificada prohibida en la ruta.")

    decoded = unquote(raw_url_path)
    if "\x00" in decoded or "\\" in decoded:
        raise PermissionError("Caracteres prohibidos tras decodificación.")

    rel = decoded.lstrip("/")
    if not rel:
        rel = "index.html"

    parts = Path(rel).parts
    if not parts:
        raise PermissionError("Ruta vacía.")

    for part in parts:
        if part in ("..", ".") or part.startswith(".") or ":" in part:
            raise PermissionError("Segmento de ruta prohibido.")

    candidate = root.joinpath(*parts)
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise FileNotFoundError("Recurso estático no encontrado.") from exc

    if not resolved.is_relative_to(root):
        raise PermissionError("Acceso denegado fuera del directorio estático.")

    if not resolved.is_file():
        raise FileNotFoundError("El recurso solicitado no es un archivo.")

    if resolved.suffix.lower() not in ALLOWED_STATIC_EXTS:
        raise PermissionError("Extensión de archivo no permitida.")

    return resolved
