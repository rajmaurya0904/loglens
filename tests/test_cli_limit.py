"""Tests for --limit, including stopping a stream that would never end on its own."""

import sys
import time
from pathlib import Path

import pytest

from tests.helpers import run_cli, write_logs


def test_limit_prints_exactly_n_lines(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    code, lines = run_cli(
        "--no-follow", "--limit", "5", "--file", str(api), "--file", str(payments)
    )
    assert code == 0
    assert len(lines) == 5


def test_limit_larger_than_input_prints_everything(tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    _, lines = run_cli("--no-follow", "--limit", "500", "--file", str(api))
    assert len(lines) == 8


def test_limit_zero_prints_nothing_and_succeeds(tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    code, lines = run_cli("--no-follow", "--limit", "0", "--file", str(api))
    assert code == 0 and lines == []


def test_limit_zero_still_reports_unusable_sources(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, _ = run_cli("--no-follow", "--limit", "0", "--file", str(tmp_path / "missing.log"))
    assert code == 2


def test_limit_counts_only_lines_that_pass_the_filters(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    _, lines = run_cli(
        "--no-follow", "--limit", "2", "--filter", "payments", "--file", str(api),
        "--file", str(payments),
    )
    assert len(lines) == 2
    assert all(line.startswith("payments") for line in lines)


def test_limit_ends_a_followed_stream(tmp_path: Path) -> None:
    """A command that prints forever must stop once the limit is reached."""
    script = tmp_path / "ticker.py"
    script.write_text(
        "import time\n"
        "while True:\n"
        "    print('2024-05-14T09:15:00Z tick', flush=True)\n"
        "    time.sleep(0.01)\n",
        encoding="utf-8",
    )
    started = time.monotonic()
    command = f'"{sys.executable}" "{script}"'
    code, lines = run_cli("--cmd", f"ticker={command}", "--limit", "3", "--window", "0.05")
    assert code == 0
    assert len(lines) == 3
    assert time.monotonic() - started < 20


def test_limit_ends_a_followed_file(tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    started = time.monotonic()
    code, lines = run_cli("--limit", "4", "--file", str(api))  # follow is the default
    assert code == 0 and len(lines) == 4
    assert time.monotonic() - started < 10
