"""Tests for the source base classes, file source and stdin source."""

import inspect
import io
import threading
import time
from pathlib import Path

import pytest

from loglens.sources import Entry, FileSource, LogLensError, LogSource, StdinSource

BASE = 1704110400.0  # 2024-01-01T12:00:00Z


def test_log_source_is_abstract() -> None:
    assert inspect.isabstract(LogSource)
    with pytest.raises(TypeError):
        LogSource()  # type: ignore[abstract]


def test_entry_unpacks_as_timestamp_service_message() -> None:
    stamp, service, message = Entry(1.5, "api", "hello")
    assert (stamp, service, message) == (1.5, "api", "hello")


def test_file_source_parses_timestamps_and_names_service_after_file(tmp_path: Path) -> None:
    log = tmp_path / "api.log"
    log.write_text(
        "2024-01-01T12:00:00Z starting\n2024-01-01T12:00:01.500Z ready on :8080\n",
        encoding="utf-8",
    )
    entries = list(FileSource(log).stream())
    assert entries == [
        Entry(BASE, "api", "starting"),
        Entry(BASE + 1.5, "api", "ready on :8080"),
    ]


def test_file_source_explicit_name(tmp_path: Path) -> None:
    log = tmp_path / "x.log"
    log.write_text("2024-01-01T12:00:00Z a\n", encoding="utf-8")
    assert list(FileSource(log, name="billing").stream())[0].service == "billing"


def test_continuation_lines_inherit_the_previous_timestamp(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text(
        "2024-01-01T12:00:00Z ERROR boom\n"
        "Traceback (most recent call last):\n"
        '  File "x.py", line 1\n'
        "2024-01-01T12:00:05Z recovered\n",
        encoding="utf-8",
    )
    stamps = [e.timestamp for e in FileSource(log).stream()]
    assert stamps == [BASE, BASE, BASE, BASE + 5]


def test_first_line_without_timestamp_uses_the_clock(tmp_path: Path) -> None:
    log = tmp_path / "app.log"
    log.write_text("no stamp here\nstill none\n", encoding="utf-8")
    entries = list(FileSource(log, clock=lambda: 42.0).stream())
    assert [e.timestamp for e in entries] == [42.0, 42.0]


def test_json_lines_keep_the_payload_and_use_its_time_field(tmp_path: Path) -> None:
    log = tmp_path / "svc.log"
    line = '{"time": "2024-01-01T12:00:03Z", "msg": "hi"}'
    log.write_text(line + "\n", encoding="utf-8")
    (entry,) = FileSource(log).stream()
    assert entry.timestamp == BASE + 3
    assert entry.message == line


def test_file_without_trailing_newline_still_yields_last_line(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_bytes(b"2024-01-01T12:00:00Z one\r\n2024-01-01T12:00:01Z two")
    assert [e.message for e in FileSource(log).stream()] == ["one", "two"]


def test_file_tail_keeps_only_last_lines(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_text("".join(f"2024-01-01T12:00:0{i}Z line{i}\n" for i in range(6)), encoding="utf-8")
    assert [e.message for e in FileSource(log, tail=2).stream()] == ["line4", "line5"]
    assert list(FileSource(log, tail=0).stream()) == []


def test_invalid_utf8_is_replaced_not_fatal(tmp_path: Path) -> None:
    log = tmp_path / "a.log"
    log.write_bytes(b"2024-01-01T12:00:00Z caf\xe9\n")
    (entry,) = FileSource(log).stream()
    assert entry.message.startswith("caf")


def test_missing_file_raises_loglens_error(tmp_path: Path) -> None:
    source = FileSource(tmp_path / "nope.log")
    with pytest.raises(LogLensError, match="not found"):
        source.check()
    with pytest.raises(LogLensError, match="not found"):
        list(source.stream())


def test_directory_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(LogLensError, match="not a regular file"):
        FileSource(tmp_path).check()


def test_follow_picks_up_appended_lines_and_stops_on_close(tmp_path: Path) -> None:
    log = tmp_path / "live.log"
    log.write_text("2024-01-01T12:00:00Z first\n", encoding="utf-8")
    source = FileSource(log, follow=True, poll_interval=0.01)
    seen: list[str] = []
    done = threading.Event()

    def reader() -> None:
        for entry in source.stream():
            seen.append(entry.message)
        done.set()

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while "first" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    with log.open("a", encoding="utf-8") as handle:
        handle.write("2024-01-01T12:00:01Z second\n2024-01-01T12:00:02Z thi")
        handle.flush()
        time.sleep(0.1)
        handle.write("rd\n")
    deadline = time.monotonic() + 5
    while "third" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    source.close()
    assert done.wait(5)
    assert seen == ["first", "second", "third"]


def test_follow_restarts_after_truncation(tmp_path: Path) -> None:
    log = tmp_path / "rot.log"
    log.write_text("2024-01-01T12:00:00Z old old old old old old\n", encoding="utf-8")
    source = FileSource(log, follow=True, poll_interval=0.01)
    seen: list[str] = []
    thread = threading.Thread(target=lambda: seen.extend(e.message for e in source.stream()))
    thread.daemon = True
    thread.start()
    deadline = time.monotonic() + 5
    while not seen and time.monotonic() < deadline:
        time.sleep(0.01)
    time.sleep(0.1)
    log.write_text("2024-01-01T12:00:09Z new\n", encoding="utf-8")
    deadline = time.monotonic() + 5
    while "new" not in seen and time.monotonic() < deadline:
        time.sleep(0.01)
    source.close()
    thread.join(5)
    assert seen[-1] == "new"


def test_stdin_source_reads_stream_lines() -> None:
    stream = io.StringIO("2024-01-01T12:00:00Z hello\r\n2024-01-01T12:00:01Z world\n")
    entries = list(StdinSource("pipe", stream).stream())
    assert entries == [Entry(BASE, "pipe", "hello"), Entry(BASE + 1, "pipe", "world")]
