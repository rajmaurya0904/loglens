"""Tests for entry filtering and level detection."""

import pytest

from loglens.filters import EntryFilter, detect_level, normalise_level
from loglens.sources import Entry, LogLensError


def e(service: str, message: str, stamp: float = 100.0) -> Entry:
    return Entry(stamp, service, message)


@pytest.mark.parametrize(
    ("message", "level"),
    [
        ("ERROR connection refused", "error"),
        ("[warn] disk almost full", "warn"),
        ("WARNING: slow query", "warn"),
        ("info: listening", "info"),
        ("2024-01-01 DEBUG cache miss", "debug"),
        ("level=error msg=boom", "error"),
        ('level="warning" msg=hmm', "warn"),
        ('{"level": "ERROR", "msg": "x"}', "error"),
        ('{"severity": "critical", "msg": "x"}', "fatal"),
        ("\x1b[31mERROR\x1b[0m colored", "error"),
        ("PANIC: out of memory", "fatal"),
        ("just a plain line", None),
        ("  File \"x.py\", line 3, in handler", None),
        ("", None),
    ],
)
def test_detect_level(message: str, level: str | None) -> None:
    assert detect_level(message) == level


def test_detect_level_ignores_level_words_deep_in_the_line() -> None:
    long_prefix = "x" * 80
    assert detect_level(f"{long_prefix} error") is None


def test_normalise_level_aliases() -> None:
    assert normalise_level("WARNING") == "warn"
    assert normalise_level(" Err ") == "error"
    assert normalise_level("nonsense") is None


def test_no_filters_pass_everything_and_report_inactive() -> None:
    flt = EntryFilter()
    assert not flt.active
    assert flt(e("a", "anything"))


def test_include_by_exact_name_and_glob() -> None:
    flt = EntryFilter(include=["api", "worker-*"])
    assert flt(e("api", "x"))
    assert flt(e("worker-eu", "x"))
    assert not flt(e("db", "x"))
    assert not flt(e("apix", "x"))
    assert flt.active


def test_exclude_wins_over_include() -> None:
    flt = EntryFilter(include=["api*"], exclude=["api-canary"])
    assert flt(e("api", "x"))
    assert not flt(e("api-canary", "x"))


def test_grep_matches_message_and_ignores_ansi() -> None:
    flt = EntryFilter(grep=r"status=5\d\d")
    assert flt(e("a", "GET /x status=503"))
    assert not flt(e("a", "GET /x status=200"))
    assert EntryFilter(grep="boom")(e("a", "\x1b[31mbo\x1b[0mom"))


def test_grep_ignore_case_and_invert() -> None:
    assert EntryFilter(grep="timeout", ignore_case=True)(e("a", "Request TIMEOUT"))
    assert not EntryFilter(grep="timeout")(e("a", "Request TIMEOUT"))
    healthcheck = EntryFilter(grep="health", invert_grep=True)
    assert not healthcheck(e("a", "GET /health 200"))
    assert healthcheck(e("a", "GET /orders 200"))


def test_invalid_regex_is_a_loglens_error() -> None:
    with pytest.raises(LogLensError, match="invalid --grep"):
        EntryFilter(grep="(unclosed")


def test_min_level_hides_lower_severities() -> None:
    flt = EntryFilter(min_level="warn")
    assert not flt(e("a", "INFO started"))
    assert flt(e("a", "WARN slow"))
    assert flt(e("a", "ERROR bad"))


def test_unknown_level_name_is_rejected() -> None:
    with pytest.raises(LogLensError, match="unknown level"):
        EntryFilter(min_level="loud")


def test_lines_without_level_inherit_from_previous_line_of_same_service() -> None:
    flt = EntryFilter(min_level="error")
    assert flt(e("a", "ERROR boom"))
    assert flt(e("a", "Traceback (most recent call last):"))
    assert not flt(e("b", "INFO fine"))
    assert not flt(e("b", "  continuation of an info line"))
    # service a is unaffected by b's levels
    assert flt(e("a", "  File x.py, line 1"))


def test_levelless_lines_pass_before_any_level_is_known() -> None:
    assert EntryFilter(min_level="error")(e("a", "plain"))


def test_since_drops_older_entries() -> None:
    flt = EntryFilter(since=100.0)
    assert not flt(e("a", "old", stamp=99.9))
    assert flt(e("a", "edge", stamp=100.0))
    assert flt.active
