"""Helpers shared by the CLI tests."""

import io
from pathlib import Path

from loglens.__main__ import main

API = """\
2024-05-14T09:15:02.104Z INFO listening on :8080
2024-05-14T09:15:03.870Z INFO GET /orders/42 200 12ms
2024-05-14T09:15:04.215Z WARN slow upstream: payments took 1480ms
2024-05-14T09:15:04.912Z ERROR POST /orders 502 upstream payments: connection reset
Traceback (most recent call last):
  File "api/handlers.py", line 88, in create_order
ConnectionResetError: [Errno 104] Connection reset by peer
2024-05-14T09:15:06.003Z INFO GET /health 200 1ms
"""

PAYMENTS = """\
2024-05-14T09:15:01.950Z INFO payments worker ready
2024-05-14T09:15:03.980Z INFO charge order=42 amount=1999 USD
2024-05-14T09:15:04.760Z ERROR stripe: read timeout after 3000ms
2024-05-14T09:15:05.100Z WARN retry queue depth=7
"""


def write_logs(directory: Path) -> tuple[Path, Path]:
    api = directory / "api.log"
    payments = directory / "payments.log"
    api.write_text(API, encoding="utf-8")
    payments.write_text(PAYMENTS, encoding="utf-8")
    return api, payments


def run_cli(*argv: str, stdin: str | None = None) -> tuple[int, list[str]]:
    """Run main() with captured stdout; returns (exit code, output lines)."""
    out = io.StringIO()
    code = main(list(argv), stdout=out, stdin=io.StringIO(stdin) if stdin is not None else None)
    return code, out.getvalue().splitlines()
