"""Punto de entrada ejecutable: python -m alvea."""

from __future__ import annotations

import argparse

from alvea.config import SETTINGS
from alvea.server.app import run_server


def main() -> None:
    parser = argparse.ArgumentParser(description="ALVEA — Estudio de Arquitectura e Inteligencia de Procesos")
    parser.add_argument("--host", default=SETTINGS.host, help="Interfaz de escucha (por defecto: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=SETTINGS.port, help="Puerto HTTP (por defecto: 8000)")
    args = parser.parse_args()
    run_server(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
