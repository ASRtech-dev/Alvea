"""Punto de entrada ejecutable: python -m alvea."""

from __future__ import annotations

import argparse
import sys

from alvea import __app_name__, __version__
from alvea.config import SETTINGS
from alvea.server.app import run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALVEA — Estudio de Arquitectura e Inteligencia de Procesos")
    parser.add_argument("--host", default=SETTINGS.host, help="Interfaz de escucha (por defecto: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=SETTINGS.port, help="Puerto HTTP inicial (por defecto: 8000)")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="Abrir el navegador automáticamente")
    parser.add_argument("--no-auto-port", action="store_true", help="No buscar otro puerto si el indicado está ocupado")
    parser.add_argument("--check", action="store_true", help="Verificar entorno y dependencias sin iniciar el servidor")
    args = parser.parse_args(argv)

    if args.check:
        print(f"{__app_name__} v{__version__} OK (Python {sys.version.split()[0]})")
        return 0

    run_server(
        host=args.host,
        port=args.port,
        open_browser=args.open_browser,
        auto_port=not args.no_auto_port,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
