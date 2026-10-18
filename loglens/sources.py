"""Log sources for loglens.

A source is anything that can produce timestamped lines: ``docker compose logs``,
``kubectl logs``, a plain file (optionally followed like ``tail -f``), standard input, or any
external command. Every source yields :class:`Entry` tuples; :mod:`loglens.merge` interleaves
them by time.
"""

from __future__ import annotations

import collections
import sys
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import IO, NamedTuple

from loglens.timestamps import extract_timestamp


class LogLensError(Exception):
    """A problem the user can act on: missing tool, unreadable file, failing command."""


class Entry(NamedTuple):
    """One log line: when it happened, which service wrote it, and the text."""

    timestamp: float
    service: str
    message: str


class LogSource(ABC):
    """Abstract base class for log sources."""

    #: Default service label for lines that do not carry their own.
    name: str = ""

    @abstractmethod
    def stream(self) -> Iterator[Entry]:
        """Yield :class:`Entry` tuples from the source, oldest first."""

    def check(self) -> None:  # noqa: B027
        """Raise :class:`LogLensError` early if the source cannot possibly work."""

    def close(self) -> None:  # noqa: B027
        """Stop the source; called from another thread to unblock :meth:`stream`."""


class _LineSource(LogSource):
    """Turns raw ``(service, text)`` pairs into stamped entries.

    A line without its own timestamp (a stack trace frame, a wrapped message) inherits the
    timestamp of the previous line from the same service so it stays glued to its parent
    after merging. If the very first line has no timestamp the receipt time is used.
    """

    def __init__(self, name: str, clock: Callable[[], float] = time.time) -> None:
        self.name = name
        self._clock = clock
        self._last: dict[str, float] = {}

    @abstractmethod
    def _raw(self) -> Iterator[tuple[str, str]]:
        """Yield ``(service, line)`` pairs, line without its trailing newline."""

    def _stamp(self, service: str, line: str) -> Entry:
        found = extract_timestamp(line)
        if found is not None:
            stamp, message = found
        else:
            stamp = self._last.get(service) or self._clock()
            message = line
        self._last[service] = stamp
        return Entry(stamp, service, message)

    def stream(self) -> Iterator[Entry]:
        for service, line in self._raw():
            yield self._stamp(service, line)


class FileSource(_LineSource):
    """Read a log file, optionally following it as it grows (like ``tail -f``)."""

    def __init__(
        self,
        path: str | Path,
        name: str | None = None,
        *,
        follow: bool = False,
        tail: int | None = None,
        poll_interval: float = 0.2,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.path = Path(path)
        super().__init__(name or self.path.stem, clock)
        self.follow = follow
        self.tail = tail
        self.poll_interval = poll_interval
        self._stop = threading.Event()

    def check(self) -> None:
        if not self.path.exists():
            raise LogLensError(f"log file not found: {self.path}")
        if not self.path.is_file():
            raise LogLensError(f"not a regular file: {self.path}")

    def close(self) -> None:
        self._stop.set()

    def _open(self) -> IO[str]:
        self.check()
        try:
            return self.path.open("r", encoding="utf-8", errors="replace", newline="")
        except OSError as exc:
            raise LogLensError(f"cannot read {self.path}: {exc.strerror or exc}") from exc

    def _raw(self) -> Iterator[tuple[str, str]]:
        with self._open() as handle:
            pending = ""
            window: collections.deque[str] | None = None
            if self.tail is not None:
                window = collections.deque(maxlen=max(self.tail, 0))
            # readline(), not iteration: tell() is disabled on a text file after next().
            for chunk in iter(handle.readline, ""):
                if not chunk.endswith("\n"):
                    pending = chunk  # last line, still being written (or no final newline)
                elif window is not None:
                    window.append(chunk)
                else:
                    yield self.name, chunk.rstrip("\r\n")
            if window is not None:
                for chunk in window:
                    yield self.name, chunk.rstrip("\r\n")
            if not self.follow:
                if pending:
                    yield self.name, pending.rstrip("\r\n")
                return
            yield from self._follow(handle, pending)

    def _follow(self, handle: IO[str], pending: str) -> Iterator[tuple[str, str]]:
        position = handle.tell()
        while not self._stop.is_set():
            chunk = handle.readline()
            if chunk:
                pending += chunk
                if pending.endswith("\n"):
                    yield self.name, pending.rstrip("\r\n")
                    pending = ""
                position = handle.tell()
                continue
            try:
                size = self.path.stat().st_size
            except OSError:
                size = position  # file briefly missing during rotation
            if size < position:  # truncated in place: start over from the top
                handle.seek(0)
                position = 0
                pending = ""
                continue
            self._stop.wait(self.poll_interval)


class StdinSource(_LineSource):
    """Read lines from a text stream, standard input by default."""

    def __init__(self, name: str = "stdin", stream: IO[str] | None = None) -> None:
        super().__init__(name)
        self._stream = stream

    def _raw(self) -> Iterator[tuple[str, str]]:
        stream = self._stream if self._stream is not None else sys.stdin
        for line in stream:
            yield self.name, line.rstrip("\r\n")
