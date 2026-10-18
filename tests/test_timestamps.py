"""Tests for timestamp parsing."""

import pytest

from loglens.timestamps import (
    extract_timestamp,
    format_timestamp,
    isoformat,
    json_timestamp,
    parse_since,
    parse_timestamp,
    split_timestamp,
)

# 2024-01-01T12:00:00Z
BASE = 1704110400.0


def test_parse_zulu() -> None:
    assert parse_timestamp("2024-01-01T12:00:00Z") == BASE


def test_parse_nanosecond_fraction_is_truncated_to_microseconds() -> None:
    assert parse_timestamp("2024-01-01T12:00:00.123456789Z") == pytest.approx(BASE + 0.123456)


def test_parse_short_fraction() -> None:
    assert parse_timestamp("2024-01-01T12:00:00.5Z") == pytest.approx(BASE + 0.5)


def test_parse_numeric_offset() -> None:
    assert parse_timestamp("2024-01-01T14:00:00+02:00") == BASE
    assert parse_timestamp("2024-01-01T07:00:00-0500") == BASE


def test_parse_space_separator_and_no_zone_means_utc() -> None:
    assert parse_timestamp("2024-01-01 12:00:00") == BASE
    assert parse_timestamp("2024-01-01 12:00:00,250") == pytest.approx(BASE + 0.25)


def test_parse_epoch_seconds_and_milliseconds() -> None:
    assert parse_timestamp("1704110400") == BASE
    assert parse_timestamp("1704110400.5") == pytest.approx(BASE + 0.5)
    assert parse_timestamp("1704110400500") == pytest.approx(BASE + 0.5)


@pytest.mark.parametrize("bad", ["", "hello", "2024-13-01T00:00:00Z", "-5", "0"])
def test_parse_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_timestamp(bad)


def test_split_leading_timestamp() -> None:
    stamp, rest = split_timestamp("2024-01-01T12:00:00Z listening on :8080")  # type: ignore[misc]
    assert stamp == BASE
    assert rest == "listening on :8080"


def test_split_bracketed_timestamp() -> None:
    stamp, rest = split_timestamp("[2024-01-01 12:00:01] INFO started")  # type: ignore[misc]
    assert stamp == BASE + 1
    assert rest == "INFO started"


def test_split_returns_none_without_timestamp() -> None:
    assert split_timestamp("INFO started 2024-01-01T12:00:00Z") is None
    assert split_timestamp("") is None


def test_split_invalid_calendar_date_is_not_a_timestamp() -> None:
    assert split_timestamp("2024-02-31T12:00:00Z oops") is None


def test_json_timestamp_reads_known_keys() -> None:
    assert json_timestamp('{"time": "2024-01-01T12:00:00Z", "msg": "x"}') == BASE
    assert json_timestamp('{"ts": 1704110400.25}') == pytest.approx(BASE + 0.25)
    assert json_timestamp('{"@timestamp": "2024-01-01T12:00:02Z"}') == BASE + 2


def test_json_timestamp_ignores_non_json_and_missing_keys() -> None:
    assert json_timestamp("plain text") is None
    assert json_timestamp("{not json") is None
    assert json_timestamp('{"msg": "no stamp"}') is None
    assert json_timestamp("[1, 2]") is None
    assert json_timestamp('{"time": true}') is None


def test_extract_prefers_leading_stamp_and_keeps_json_whole() -> None:
    assert extract_timestamp("2024-01-01T12:00:00Z hi") == (BASE, "hi")
    line = '{"time": "2024-01-01T12:00:00Z", "msg": "hi"}'
    assert extract_timestamp(line) == (BASE, line)
    assert extract_timestamp("nothing here") is None


def test_format_helpers() -> None:
    assert format_timestamp(BASE + 0.1234) == "12:00:00.123"
    assert format_timestamp(BASE, precision=0) == "12:00:00"
    assert isoformat(BASE) == "2024-01-01T12:00:00.000000Z"


def test_parse_since_relative_durations() -> None:
    assert parse_since("30s", BASE) == BASE - 30
    assert parse_since("10m", BASE) == BASE - 600
    assert parse_since("2h", BASE) == BASE - 7200
    assert parse_since("1h30m", BASE) == BASE - 5400
    assert parse_since("1d", BASE) == BASE - 86400
    assert parse_since("0.5m", BASE) == BASE - 30


def test_parse_since_absolute_values() -> None:
    assert parse_since("2024-01-01T11:00:00Z", BASE) == BASE - 3600
    assert parse_since("1704110000", BASE) == 1704110000


@pytest.mark.parametrize("bad", ["", "soon", "10x", "m10", "5 minutes ago"])
def test_parse_since_rejects_garbage(bad: str) -> None:
    with pytest.raises(ValueError, match="invalid time"):
        parse_since(bad, BASE)


def test_utc_and_gmt_suffixes_are_consumed() -> None:
    assert split_timestamp("2024-01-01 12:00:00 UTC db ready") == (BASE, "db ready")
    assert split_timestamp("2024-01-01T12:00:00GMT x") == (BASE, "x")
    assert parse_timestamp("2024-01-01 12:00:00 UTC") == BASE
