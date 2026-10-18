"""End-to-end tests that run loglens as a real process."""

import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tests.helpers import write_logs


def run(
    *args: str, input_text: str | None = None, timeout: float = 60
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "loglens", *args],
        input=input_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
    )


def test_module_help_runs() -> None:
    result = run("--help")
    assert result.returncode == 0
    assert result.stdout.startswith("usage: loglens")


def test_console_script_is_installed_and_runs() -> None:
    exe = shutil.which("loglens", path=str(Path(sys.executable).parent))
    if exe is None:
        pytest.skip("loglens console script is not installed next to this interpreter")
    result = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=60)
    assert result.returncode == 0
    assert result.stdout.startswith("loglens ")


def test_merges_files_end_to_end(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    result = run("--no-follow", "--file", str(api), "--file", str(payments), "--limit", "3")
    assert result.returncode == 0
    assert result.stderr == ""
    lines = result.stdout.splitlines()
    assert [line.split("|")[0].strip() for line in lines] == ["payments", "api", "api"]


def test_reads_a_pipe_on_stdin() -> None:
    result = run(
        "--no-follow",
        "--file",
        "app=-",
        input_text="2024-05-14T09:15:00Z café ✓ done\n",
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "app | 09:15:00.000 café ✓ done"


def test_error_exit_code_and_message_for_missing_file(tmp_path: Path) -> None:
    result = run("--no-follow", "--file", str(tmp_path / "gone.log"))
    assert result.returncode == 2
    assert result.stdout == ""
    assert result.stderr.startswith("loglens: error: log file not found")


def test_usage_error_exit_code() -> None:
    result = run("--limit", "many")
    assert result.returncode == 2
    assert "usage: loglens" in result.stderr


def test_follows_files_live_and_merges_new_lines(tmp_path: Path) -> None:
    a = tmp_path / "a.log"
    b = tmp_path / "b.log"
    a.write_text("2024-05-14T09:15:00Z a-one\n", encoding="utf-8")
    b.write_text("2024-05-14T09:15:01Z b-one\n", encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, "-m", "loglens", "--file", str(a), "--file", str(b), "--limit", "4",
         "--window", "0.2"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    try:
        time.sleep(1.5)  # let it start and read the first lines
        with a.open("a", encoding="utf-8") as handle:
            handle.write("2024-05-14T09:15:02Z a-two\n")
        with b.open("a", encoding="utf-8") as handle:
            handle.write("2024-05-14T09:15:03Z b-two\n")
        stdout, stderr = proc.communicate(timeout=30)
    finally:
        if proc.poll() is None:
            proc.kill()
    assert proc.returncode == 0, stderr
    assert [line.split("|")[1].split()[1] for line in stdout.splitlines()] == [
        "a-one",
        "b-one",
        "a-two",
        "b-two",
    ]
