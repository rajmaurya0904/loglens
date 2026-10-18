"""ANSI colour helpers for loglens."""

from __future__ import annotations

import re
import zlib

RESET = "\x1b[0m"

# Foreground codes used for service names. Red is left out on purpose so that error lines,
# which are painted red, stand out from any service prefix.
PALETTE: tuple[int, ...] = (32, 33, 34, 35, 36, 92, 93, 94, 95, 96)

_ANSI_RE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07\x1b]*(?:\x07|\x1b\\)|[@-Z\\-_])")


def color_code(service: str) -> int:
    """Return the ANSI foreground code for a service.

    The choice is a CRC of the name, so a service keeps its colour across runs and machines
    (the builtin ``hash`` is randomised per Python process and would not).
    """
    return PALETTE[zlib.crc32(service.encode("utf-8")) % len(PALETTE)]


def colorize(line: str, service: str) -> str:
    """Wrap ``line`` in the ANSI colour assigned to ``service``."""
    return f"\x1b[{color_code(service)}m{line}{RESET}"


def paint(text: str, code: int | str, *, bold: bool = False) -> str:
    """Wrap ``text`` in an arbitrary SGR code, optionally bold."""
    prefix = "1;" if bold else ""
    return f"\x1b[{prefix}{code}m{text}{RESET}"


def strip_ansi(text: str) -> str:
    """Remove ANSI escape sequences (colours, cursor moves) from ``text``."""
    return _ANSI_RE.sub("", text)
