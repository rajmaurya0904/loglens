"""Deciding which merged entries are shown: by service, text, level and age."""

from __future__ import annotations

import fnmatch
import json
import re
from collections.abc import Sequence

from loglens.color import strip_ansi
from loglens.sources import Entry, LogLensError

LEVELS = {"trace": 0, "debug": 1, "info": 2, "warn": 3, "error": 4, "fatal": 5}

_ALIASES = {
    "warning": "warn",
    "err": "error",
    "critical": "fatal",
    "crit": "fatal",
    "panic": "fatal",
    "emerg": "fatal",
    "alert": "fatal",
    "notice": "info",
    "verbose": "trace",
    "dbg": "debug",
}

_LOGFMT_LEVEL = re.compile(r"\b(?:level|lvl|severity)=\"?([A-Za-z]+)")
_TOKEN_LEVEL = re.compile(
    r"(?:^|[\s\[(<|])"
    r"(trace|debug|dbg|info|notice|warn|warning|err|error|crit|critical|fatal|panic|emerg|alert)"
    r"(?=$|[\s\])>:|,])",
    re.IGNORECASE,
)
_PREFIX_CHARS = 48  # only look at the start of the line for a bare level word
_JSON_LEVEL_KEYS = ("level", "severity", "lvl", "log.level")


def normalise_level(word: str) -> str | None:
    """Map a level word (``WARNING``, ``err``, ...) to one of :data:`LEVELS`, or ``None``."""
    word = word.strip().lower()
    word = _ALIASES.get(word, word)
    return word if word in LEVELS else None


def detect_level(message: str) -> str | None:
    """Guess the severity of a log message; ``None`` when nothing recognisable is there.

    Looks at a JSON ``level`` field, a ``level=...`` logfmt pair, then a level word near the
    start of the line (``ERROR``, ``[warn]``, ``info:``). It is a heuristic: free-form text
    that merely starts with the word "error" is treated as an error.
    """
    text = strip_ansi(message).strip()
    if text.startswith("{"):
        try:
            record = json.loads(text)
        except ValueError:
            record = None
        if isinstance(record, dict):
            for key in _JSON_LEVEL_KEYS:
                value = record.get(key)
                if isinstance(value, str) and normalise_level(value):
                    return normalise_level(value)
    match = _LOGFMT_LEVEL.search(text)
    if match and normalise_level(match.group(1)):
        return normalise_level(match.group(1))
    match = _TOKEN_LEVEL.search(text[:_PREFIX_CHARS])
    if match:
        return normalise_level(match.group(1))
    return None


class EntryFilter:
    """Predicate over merged entries.

    ``include`` and ``exclude`` take exact service names or shell-style globs (``api*``).
    ``grep`` is a regular expression searched in the message. ``min_level`` hides lines below
    that severity; lines with no recognisable level (stack trace frames, for instance) share
    the level of the previous line from the same service. ``since`` drops older entries.
    """

    def __init__(
        self,
        include: Sequence[str] = (),
        exclude: Sequence[str] = (),
        *,
        grep: str | None = None,
        ignore_case: bool = False,
        invert_grep: bool = False,
        min_level: str | None = None,
        since: float | None = None,
    ) -> None:
        self.include = list(include)
        self.exclude = list(exclude)
        self.invert_grep = invert_grep
        self.since = since
        self._pattern: re.Pattern[str] | None = None
        if grep is not None:
            try:
                self._pattern = re.compile(grep, re.IGNORECASE if ignore_case else 0)
            except re.error as exc:
                raise LogLensError(f"invalid --grep pattern {grep!r}: {exc}") from exc
        self.min_rank: int | None = None
        if min_level is not None:
            level = normalise_level(min_level)
            if level is None:
                choices = ", ".join(LEVELS)
                raise LogLensError(f"unknown level {min_level!r}; choose one of: {choices}")
            self.min_rank = LEVELS[level]
        self._service_level: dict[str, str] = {}

    @property
    def active(self) -> bool:
        """True when this filter can reject anything at all."""
        return bool(
            self.include
            or self.exclude
            or self._pattern
            or self.min_rank is not None
            or self.since is not None
        )

    @staticmethod
    def _service_matches(service: str, patterns: Sequence[str]) -> bool:
        return any(service == p or fnmatch.fnmatchcase(service, p) for p in patterns)

    def __call__(self, entry: Entry) -> bool:
        if self.since is not None and entry.timestamp < self.since:
            return False
        if self.include and not self._service_matches(entry.service, self.include):
            return False
        if self.exclude and self._service_matches(entry.service, self.exclude):
            return False
        if self._pattern is not None:
            found = self._pattern.search(strip_ansi(entry.message)) is not None
            if found == self.invert_grep:
                return False
        if self.min_rank is not None:
            level = detect_level(entry.message)
            if level is None:
                level = self._service_level.get(entry.service)
            else:
                self._service_level[entry.service] = level
            if level is not None and LEVELS[level] < self.min_rank:
                return False
        return True
