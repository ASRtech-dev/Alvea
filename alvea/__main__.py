"""Executable entry point: python -m alvea."""

from __future__ import annotations

import argparse
import sys

from alvea import __app_name__, __version__
from alvea.config import SETTINGS
from alvea.server.app import run_server


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ALVEA — Process Architecture & Intelligence Studio")
    parser.add_argument("--host", default=SETTINGS.host, help="Bind interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=SETTINGS.port, help="Initial HTTP port (default: 8000)")
    parser.add_argument("--open", dest="open_browser", action="store_true", help="Open default browser automatically")
    parser.add_argument("--no-auto-port", action="store_true", help="Fail instead of scanning next free port")
    parser.add_argument("--check", action="store_true", help="Verify runtime environment without starting server")
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
