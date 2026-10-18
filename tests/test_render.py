"""Tests for output formatting."""

import json

from loglens.color import color_code, strip_ansi
from loglens.render import Formatter
from loglens.sources import Entry

BASE = 1704110400.0


def test_plain_format_has_service_time_and_message() -> None:
    line = Formatter().format(Entry(BASE + 0.25, "api", "listening"))
    assert line == "api | 12:00:00.250 listening"


def test_columns_widen_to_the_longest_service_seen() -> None:
    fmt = Formatter(show_time=False)
    assert fmt.format(Entry(BASE, "db", "a")) == "db | a"
    assert fmt.format(Entry(BASE, "gateway", "b")) == "gateway | b"
    assert fmt.format(Entry(BASE, "db", "c")) == "db      | c"


def test_time_can_be_hidden_and_precision_changed() -> None:
    assert Formatter(show_time=False).format(Entry(BASE, "a", "m")) == "a | m"
    assert Formatter(precision=0).format(Entry(BASE, "a", "m")) == "a | 12:00:00 m"


def test_plain_output_strips_embedded_ansi() -> None:
    line = Formatter().format(Entry(BASE, "a", "\x1b[32mgreen\x1b[0m text"))
    assert "\x1b" not in line
    assert line.endswith("green text")


def test_colour_output_uses_service_colour_for_prefix() -> None:
    line = Formatter(color=True).format(Entry(BASE, "api", "hello"))
    assert line.startswith(f"\x1b[1;{color_code('api')}m")
    assert strip_ansi(line) == "api | 12:00:00.000 hello"


def test_colour_output_paints_errors_red_and_warnings_yellow() -> None:
    fmt = Formatter(color=True)
    assert "\x1b[31mERROR boom\x1b[0m" in fmt.format(Entry(BASE, "a", "ERROR boom"))
    assert "\x1b[33mWARN hmm\x1b[0m" in fmt.format(Entry(BASE, "a", "WARN hmm"))
    assert "\x1b[31m" not in fmt.format(Entry(BASE, "a", "INFO fine"))


def test_colour_output_keeps_existing_message_ansi() -> None:
    line = Formatter(color=True).format(Entry(BASE, "a", "\x1b[32mgreen\x1b[0m"))
    assert "\x1b[32mgreen" in line


def test_json_lines_output_is_valid_json() -> None:
    line = Formatter(json_lines=True).format(Entry(BASE, "api", "café \x1b[31mred\x1b[0m"))
    assert json.loads(line) == {
        "time": "2024-01-01T12:00:00.000000Z",
        "service": "api",
        "message": "café red",
    }
