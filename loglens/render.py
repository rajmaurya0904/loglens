"""Turning merged entries into output lines."""

from __future__ import annotations

import json

from loglens.color import color_code, paint, strip_ansi
from loglens.filters import detect_level
from loglens.sources import Entry
from loglens.timestamps import format_timestamp, isoformat

_LEVEL_STYLE = {"fatal": "1;31", "error": "31", "warn": "33"}


class Formatter:
    """Format entries as ``service | HH:MM:SS.mmm message``, or as JSON lines.

    The service column grows to fit the longest name seen so far, so columns line up without
    needing to know the service list in advance; pass ``width`` to start wide enough when the
    names are known up front. With ``color`` on, the prefix takes the
    service's colour and error and warning lines are painted red and yellow; with it off,
    any ANSI codes already in the messages are stripped so the output is safe to pipe.
    """

    def __init__(
        self,
        *,
        color: bool = False,
        show_time: bool = True,
        precision: int = 3,
        json_lines: bool = False,
        width: int = 0,
    ) -> None:
        self.color = color
        self.show_time = show_time
        self.precision = precision
        self.json_lines = json_lines
        self._width = width

    def format(self, entry: Entry) -> str:
        if self.json_lines:
            return self._format_json(entry)
        self._width = max(self._width, len(entry.service))
        message = entry.message if self.color else strip_ansi(entry.message)
        name = entry.service.ljust(self._width)
        stamp = ""
        if self.show_time:
            stamp = format_timestamp(entry.timestamp, precision=self.precision) + " "
        if not self.color:
            return f"{name} | {stamp}{message}"
        prefix = paint(f"{name} |", color_code(entry.service), bold=True)
        style = _LEVEL_STYLE.get(detect_level(message) or "")
        if style:
            message = paint(message, style)
        return f"{prefix} {stamp}{message}"

    def _format_json(self, entry: Entry) -> str:
        record = {
            "time": isoformat(entry.timestamp),
            "service": entry.service,
            "message": strip_ansi(entry.message),
        }
        return json.dumps(record, ensure_ascii=False)
