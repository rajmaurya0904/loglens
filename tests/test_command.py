"""Tests for CommandSource, which runs real subprocesses."""

import sys
import time

import pytest

from loglens.sources import CommandSource, Entry, LogLensError

BASE = 1704110400.0


def py(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def test_command_source_streams_stdout_lines() -> None:
    code = (
        "print('2024-01-01T12:00:00Z one'); print('2024-01-01T12:00:01Z two')"
    )
    entries = list(CommandSource("job", py(code)).stream())
    assert entries == [Entry(BASE, "job", "one"), Entry(BASE + 1, "job", "two")]


def test_command_source_check_accepts_existing_executable() -> None:
    CommandSource("job", py("pass")).check()


def test_missing_executable_raises_clear_error() -> None:
    source = CommandSource("job", ["definitely-not-a-real-binary-xyz", "--flag"])
    with pytest.raises(LogLensError, match="definitely-not-a-real-binary-xyz.*not found"):
        source.check()
    with pytest.raises(LogLensError, match="not found"):
        list(source.stream())


def test_empty_command_is_rejected() -> None:
    with pytest.raises(LogLensError, match="empty command"):
        CommandSource("job", [])


def test_nonzero_exit_raises_with_stderr_detail() -> None:
    code = "import sys; print('2024-01-01T12:00:00Z hi'); sys.stderr.write('kaboom'); sys.exit(3)"
    source = CommandSource("job", py(code))
    stream = source.stream()
    assert next(stream).message == "hi"
    with pytest.raises(LogLensError, match=r"status 3.*kaboom"):
        next(stream)


def test_zero_exit_with_no_output_is_fine() -> None:
    assert list(CommandSource("job", py("pass")).stream()) == []


def test_lines_without_timestamp_get_receipt_time() -> None:
    before = time.time()
    (entry,) = CommandSource("job", py("print('bare line')")).stream()
    assert before <= entry.timestamp <= time.time()
    assert entry.message == "bare line"


def test_close_terminates_a_long_running_command() -> None:
    code = "import time; print('2024-01-01T12:00:00Z up', flush=True); time.sleep(60)"
    source = CommandSource("job", py(code))
    stream = source.stream()
    assert next(stream).message == "up"
    source.close()
    started = time.monotonic()
    assert list(stream) == []
    assert time.monotonic() - started < 10


def test_reconnect_reruns_and_skips_replayed_lines(tmp_path) -> None:
    marker = tmp_path / "runs.txt"
    code = f"""
import pathlib
m = pathlib.Path({str(marker)!r})
n = int(m.read_text()) if m.exists() else 0
m.write_text(str(n + 1))
print('2024-01-01T12:00:00Z first')
if n == 0:
    print('2024-01-01T12:00:01Z second')
else:
    print('2024-01-01T12:00:01Z second')
    print('2024-01-01T12:00:02Z third')
"""
    source = CommandSource("job", py(code), reconnect=True, retry_delay=0.01)
    stream = source.stream()
    got = [next(stream).message for _ in range(3)]
    source.close()
    assert got == ["first", "second", "third"]
    assert marker.read_text() == "2"


def test_reconnect_gives_up_after_repeated_failures() -> None:
    source = CommandSource("job", py("import sys; sys.exit(1)"), reconnect=True, retry_delay=0)
    source.MAX_FAILURES = 3
    with pytest.raises(LogLensError, match="status 1"):
        list(source.stream())
