"""Tests for merging interleaved streams."""

import threading
import time
from collections.abc import Iterator

import pytest

from loglens.merge import LiveMerger, merge_streams
from loglens.sources import Entry, LogLensError, LogSource


class ListSource(LogSource):
    """A source that replays a fixed list, optionally pausing between entries."""

    def __init__(
        self, name: str, entries: list[Entry], *, delay: float = 0.0, error: Exception | None = None
    ) -> None:
        self.name = name
        self.entries = entries
        self.delay = delay
        self.error = error
        self.closed = threading.Event()
        self.checked = False

    def check(self) -> None:
        self.checked = True

    def close(self) -> None:
        self.closed.set()

    def stream(self) -> Iterator[Entry]:
        for entry in self.entries:
            if self.delay:
                time.sleep(self.delay)
            yield entry
        if self.error is not None:
            raise self.error


def e(stamp: float, service: str, message: str) -> Entry:
    return Entry(stamp, service, message)


def test_merge_streams_orders_overlapping_sources_chronologically() -> None:
    a = ListSource("a", [e(1, "a", "a1"), e(3, "a", "a3"), e(5, "a", "a5")])
    b = ListSource("b", [e(2, "b", "b2"), e(4, "b", "b4"), e(6, "b", "b6")])
    assert [x.message for x in merge_streams([a, b])] == ["a1", "b2", "a3", "b4", "a5", "b6"]


def test_merge_streams_accepts_plain_iterables_and_empty_input() -> None:
    assert list(merge_streams([])) == []
    merged = merge_streams([[e(2, "x", "late")], iter([e(1, "y", "early")])])
    assert [x.message for x in merged] == ["early", "late"]


def test_merge_streams_is_stable_for_equal_timestamps() -> None:
    a = ListSource("a", [e(1, "a", "first")])
    b = ListSource("b", [e(1, "b", "second")])
    assert [x.service for x in merge_streams([a, b])] == ["a", "b"]


def test_merge_streams_handles_unequal_lengths() -> None:
    a = ListSource("a", [e(1, "a", "1")])
    b = ListSource("b", [e(i, "b", str(i)) for i in range(2, 6)])
    assert [x.timestamp for x in merge_streams([a, b])] == [1, 2, 3, 4, 5]


def test_live_merger_orders_finite_sources_completely() -> None:
    a = ListSource("a", [e(1, "a", "a1"), e(3, "a", "a3"), e(5, "a", "a5")])
    b = ListSource("b", [e(2, "b", "b2"), e(4, "b", "b4")])
    merger = LiveMerger([a, b], window=5)
    assert [x.message for x in merger] == ["a1", "b2", "a3", "b4", "a5"]
    assert a.checked and b.checked


def test_live_merger_with_no_sources_ends_immediately() -> None:
    assert list(LiveMerger([])) == []


def test_live_merger_reorders_when_slow_source_arrives_late() -> None:
    # b's older line arrives after a's newer one; the window holds a's line back.
    fast = ListSource("fast", [e(10, "fast", "newer")])
    slow = ListSource("slow", [e(5, "slow", "older")], delay=0.15)
    assert [x.message for x in LiveMerger([fast, slow], window=2)] == ["older", "newer"]


def test_live_merger_releases_after_window_when_a_source_stays_quiet() -> None:
    quiet_gate = threading.Event()

    class Quiet(ListSource):
        def stream(self) -> Iterator[Entry]:
            quiet_gate.wait(10)
            return iter(())

    chatty = ListSource("chatty", [e(1, "chatty", "hello")])
    merger = LiveMerger([chatty, Quiet("quiet", [])], window=0.1)
    started = time.monotonic()
    iterator = iter(merger)
    first = next(iterator)
    elapsed = time.monotonic() - started
    quiet_gate.set()
    iterator.close()
    assert first.message == "hello"
    assert 0.05 < elapsed < 5


def test_live_merger_closes_sources_when_consumer_stops_early() -> None:
    a = ListSource("a", [e(i, "a", str(i)) for i in range(100)], delay=0.001)
    b = ListSource("b", [e(i + 0.5, "b", str(i)) for i in range(100)], delay=0.001)
    merger = LiveMerger([a, b], window=0.05)
    taken = []
    for entry in merger:
        taken.append(entry)
        if len(taken) == 5:
            break
    assert len(taken) == 5
    assert a.closed.is_set() and b.closed.is_set()


def test_live_merger_propagates_source_errors_after_ready_entries() -> None:
    good = ListSource("good", [e(1, "good", "ok")])
    bad = ListSource("bad", [e(2, "bad", "before-crash")], error=LogLensError("kubectl exploded"))
    merger = LiveMerger([good, bad], window=0.05)
    seen = []
    with pytest.raises(LogLensError, match="kubectl exploded"):
        for entry in merger:
            seen.append(entry.message)
    assert seen == ["ok", "before-crash"]


def test_live_merger_check_failure_happens_before_any_output() -> None:
    class Broken(ListSource):
        def check(self) -> None:
            raise LogLensError("not installed")

    merger = LiveMerger([ListSource("a", [e(1, "a", "x")]), Broken("b", [])])
    with pytest.raises(LogLensError, match="not installed"):
        next(iter(merger))
