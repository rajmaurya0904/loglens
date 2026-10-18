"""Tests for ANSI colour helpers."""

import os
import subprocess
import sys

from loglens.color import PALETTE, color_code, colorize, paint, strip_ansi


def test_colorize_wraps_line_in_ansi_codes() -> None:
    colored = colorize("test message", "myservice")
    assert colored.startswith("\x1b[")
    assert colored.endswith("\x1b[0m")
    assert "test message" in colored


def test_colorize_is_consistent_for_a_service() -> None:
    assert colorize("same", "service-a") == colorize("same", "service-a")


def test_different_services_get_different_codes() -> None:
    codes = {color_code(f"service-{c}") for c in "abcdefgh"}
    assert len(codes) > 3


def test_codes_come_from_palette_and_exclude_red() -> None:
    for name in ("api", "db", "web", "worker", "cache", "queue"):
        assert color_code(name) in PALETTE
    assert 31 not in PALETTE and 91 not in PALETTE


def test_colour_is_stable_across_python_processes() -> None:
    """The builtin hash() is randomised per process; the colour must not be."""
    code = "from loglens.color import color_code; print(color_code('payments'))"
    outputs = set()
    for seed in ("1", "2", "3"):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, check=True, env=env
        )
        outputs.add(result.stdout.strip())
    assert outputs == {str(color_code("payments"))}


def test_paint_supports_bold() -> None:
    assert paint("x", 31) == "\x1b[31mx\x1b[0m"
    assert paint("x", 31, bold=True) == "\x1b[1;31mx\x1b[0m"


def test_strip_ansi_removes_colour_and_cursor_sequences() -> None:
    text = "\x1b[1;31mred\x1b[0m plain \x1b[2K\x1b[10;5H done"
    assert strip_ansi(text) == "red plain  done"


def test_strip_ansi_roundtrips_colorize() -> None:
    assert strip_ansi(colorize("hello", "api")) == "hello"
    assert strip_ansi(paint("hello", 36)) == "hello"
