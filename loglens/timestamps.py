"""Timestamp parsing for log lines.

Docker, kubectl and most application loggers emit RFC 3339 / ISO 8601 stamps, often with
nanosecond precision (``2024-01-01T12:00:00.123456789Z``) which :func:`datetime.fromisoformat`
does not accept. This module parses those by hand and also knows how to pull a timestamp out
of the front of a free-form line or out of a JSON log record.

Timestamps without a UTC offset are treated as UTC.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta, timezone

# 2024-01-01T12:00:00(.123456789)?(Z|+01:00|+0100)?  -- 'T' may be a space.
_ISO_RE = re.compile(
    r"(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})"
    r"[T ](?P<hour>\d{2}):(?P<minute>\d{2}):(?P<second>\d{2})"
    r"(?:[.,](?P<frac>\d+))?"
    r"(?P<tz>Z|z|[+-]\d{2}:?\d{2})?"
)

# A leading timestamp, optionally wrapped in [] or (), followed by whitespace or a separator.
_LEADING_RE = re.compile(r"^[\[(]?\s*(" + _ISO_RE.pattern.replace("?P<", "?P<l_") + r")[\])]?")

_JSON_KEYS = ("timestamp", "time", "ts", "@timestamp", "t", "datetime")

# Epoch values below this are seconds, above are milliseconds (year 2001 in ms is 9.9e11).
_EPOCH_MS_THRESHOLD = 1e11


def _build(match: re.Match[str], prefix: str = "") -> float:
    g = match.groupdict()
    frac = g[f"{prefix}frac"] or ""
    micro = int((frac + "000000")[:6]) if frac else 0
    tz_text = g[f"{prefix}tz"]
    if tz_text and tz_text not in ("Z", "z"):
        sign = 1 if tz_text[0] == "+" else -1
        digits = tz_text[1:].replace(":", "")
        offset = timedelta(hours=int(digits[:2]), minutes=int(digits[2:4]))
        tz = timezone(sign * offset)
    else:
        tz = UTC
    try:
        moment = datetime(
            int(g[f"{prefix}year"]),
            int(g[f"{prefix}month"]),
            int(g[f"{prefix}day"]),
            int(g[f"{prefix}hour"]),
            int(g[f"{prefix}minute"]),
            int(g[f"{prefix}second"]),
            micro,
            tzinfo=tz,
        )
    except ValueError as exc:
        raise ValueError(f"invalid timestamp: {match.group(0)!r}") from exc
    return moment.timestamp()


def parse_timestamp(text: str) -> float:
    """Parse a complete timestamp string into seconds since the Unix epoch.

    Accepts ISO 8601 / RFC 3339 (any fraction length, ``Z`` or numeric offset, ``T`` or space
    separator) and plain epoch numbers in seconds or milliseconds. Raises ``ValueError`` when
    the text is not a timestamp.
    """
    text = text.strip()
    match = _ISO_RE.fullmatch(text)
    if match:
        return _build(match)
    try:
        number = float(text)
    except ValueError:
        raise ValueError(f"unrecognised timestamp: {text!r}") from None
    if number <= 0:
        raise ValueError(f"unrecognised timestamp: {text!r}")
    return number / 1000.0 if number >= _EPOCH_MS_THRESHOLD else number


def split_timestamp(line: str) -> tuple[float, str] | None:
    """Split a leading timestamp off ``line``.

    Returns ``(epoch_seconds, remainder)`` where the remainder has the timestamp and one
    separating space removed, or ``None`` when the line does not start with a timestamp.
    """
    match = _LEADING_RE.match(line)
    if not match:
        return None
    try:
        stamp = _build(match, "l_")
    except ValueError:
        return None
    rest = line[match.end() :]
    if rest.startswith((" ", "\t")):
        rest = rest[1:]
    return stamp, rest


def json_timestamp(line: str) -> float | None:
    """Return the timestamp of a JSON log record, or ``None`` if there is not one."""
    stripped = line.lstrip()
    if not stripped.startswith("{"):
        return None
    try:
        record = json.loads(stripped)
    except ValueError:
        return None
    if not isinstance(record, dict):
        return None
    for key in _JSON_KEYS:
        value = record.get(key)
        if value is None or isinstance(value, bool):
            continue
        try:
            return parse_timestamp(str(value))
        except ValueError:
            continue
    return None


def extract_timestamp(line: str) -> tuple[float, str] | None:
    """Find a timestamp in ``line``: leading ISO stamp first, then a JSON field.

    For a JSON record the line is returned unchanged since the stamp is part of the payload.
    """
    found = split_timestamp(line)
    if found is not None:
        return found
    stamp = json_timestamp(line)
    if stamp is not None:
        return stamp, line
    return None


def format_timestamp(epoch: float, *, precision: int = 3) -> str:
    """Format epoch seconds as an UTC ``HH:MM:SS.mmm`` clock string."""
    moment = datetime.fromtimestamp(epoch, tz=UTC)
    base = moment.strftime("%H:%M:%S")
    if precision <= 0:
        return base
    micro = f"{moment.microsecond:06d}"[: min(precision, 6)]
    return f"{base}.{micro}"


def isoformat(epoch: float) -> str:
    """Format epoch seconds as an RFC 3339 UTC timestamp with microseconds."""
    return datetime.fromtimestamp(epoch, tz=UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
