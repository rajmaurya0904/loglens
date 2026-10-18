"""Merging several log streams into one time-ordered stream.

Two tools are provided:

* :func:`merge_streams` -- a plain ``heapq.merge`` over streams that are each already sorted.
  Right for finite inputs such as files that are read to the end.
* :class:`LiveMerger` -- runs every source on its own thread and merges what arrives. Live
  streams cannot be sorted perfectly because a quiet service might still emit a line that
  happened earlier, so a line is released once every active source has caught up past it,
  or once it has waited ``window`` seconds, whichever comes first.
"""

from __future__ import annotations

import heapq
import itertools
import queue
import threading
import time
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from loglens.sources import Entry, LogSource


def merge_streams(sources: Iterable[LogSource | Iterable[Entry]]) -> Iterator[Entry]:
    """Merge streams that are individually sorted into one chronological stream.

    Each item may be a :class:`LogSource` or any iterable of :class:`Entry`. Entries with equal
    timestamps keep the order of the sources they came from.
    """
    streams = [s.stream() if isinstance(s, LogSource) else iter(s) for s in sources]
    return heapq.merge(*streams, key=lambda entry: entry.timestamp)


_DONE = object()


@dataclass(order=True)
class _Held:
    timestamp: float
    seq: int
    arrived: float = field(compare=False)
    entry: Entry = field(compare=False)


class LiveMerger:
    """Merge sources that are still producing output.

    Iterate over the merger to receive entries. Leaving the loop early (``break``, an
    exception, ``close()``) stops every source. A :class:`~loglens.sources.LogLensError` raised
    by any source is re-raised from the iterator after the entries that were already ready.
    """

    def __init__(
        self,
        sources: Iterable[LogSource],
        *,
        window: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.sources = list(sources)
        self.window = window
        self._clock = clock
        self._queue: queue.Queue[tuple[int, object]] = queue.Queue()
        self._threads: list[threading.Thread] = []
        self._closed = False

    def _pump(self, index: int, source: LogSource) -> None:
        try:
            for entry in source.stream():
                self._queue.put((index, entry))
        except BaseException as exc:  # forwarded to the consumer thread
            self._queue.put((index, exc))
        finally:
            self._queue.put((index, _DONE))

    def start(self) -> None:
        """Check every source, then launch the reader threads."""
        if self._threads:
            return
        for source in self.sources:
            source.check()
        for index, source in enumerate(self.sources):
            thread = threading.Thread(
                target=self._pump, args=(index, source), name=f"loglens-{source.name}", daemon=True
            )
            thread.start()
            self._threads.append(thread)

    def close(self) -> None:
        """Ask every source to stop and wait briefly for the reader threads."""
        self._closed = True
        for source in self.sources:
            source.close()
        for thread in self._threads:
            thread.join(timeout=2)

    def __iter__(self) -> Iterator[Entry]:
        try:
            self.start()
            yield from self._run()
        finally:
            self.close()

    def _run(self) -> Iterator[Entry]:
        held: list[_Held] = []
        counter = itertools.count()
        # Latest timestamp seen per source; None until the source has produced something.
        latest: dict[int, float | None] = {i: None for i in range(len(self.sources))}
        active = set(latest)
        failure: BaseException | None = None

        while active or held:
            timeout = self._wait_time(held)
            try:
                index, item = self._queue.get(timeout=timeout)
            except queue.Empty:
                pass
            else:
                while True:
                    if item is _DONE:
                        active.discard(index)
                    elif isinstance(item, BaseException):
                        failure = failure or item
                    elif isinstance(item, Entry):
                        stamp = item.timestamp
                        previous = latest[index]
                        latest[index] = stamp if previous is None else max(previous, stamp)
                        heapq.heappush(held, _Held(stamp, next(counter), self._clock(), item))
                    try:
                        index, item = self._queue.get_nowait()
                    except queue.Empty:
                        break
            yield from self._release(held, latest, active, flush=failure is not None)
            if failure is not None:
                raise failure

    def _wait_time(self, held: list[_Held]) -> float:
        """How long to block for the next arrival before something must be re-evaluated."""
        if not held:
            return 0.25
        age = self._clock() - held[0].arrived
        return min(0.25, max(0.0, self.window - age))

    def _release(
        self,
        held: list[_Held],
        latest: dict[int, float | None],
        active: set[int],
        *,
        flush: bool,
    ) -> Iterator[Entry]:
        while held:
            top = held[0]
            if not flush and active:
                marks = [latest[i] for i in active]
                caught_up = all(m is not None and m >= top.timestamp for m in marks)
                waited = self._clock() - top.arrived >= self.window
                if not (caught_up or waited):
                    return
            heapq.heappop(held)
            yield top.entry
