"""Shared fixtures: stand-in ``docker`` / ``kubectl`` executables placed on PATH."""

import json
import os
import stat
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

SHIM = r"""
import json, os, sys
here = os.path.dirname(os.path.abspath(__file__))
name = sys.argv[1]
with open(os.path.join(here, name + ".argv.json"), "a", encoding="utf-8") as fh:
    fh.write(json.dumps(sys.argv[2:]) + "\n")
spec = json.load(open(os.path.join(here, name + ".spec.json"), encoding="utf-8"))
runs = os.path.join(here, name + ".runs")
n = int(open(runs).read()) if os.path.exists(runs) else 0
open(runs, "w").write(str(n + 1))
outputs = spec["outputs"]
out = outputs[min(n, len(outputs) - 1)]
sys.stdout.buffer.write(out.encode("utf-8"))
sys.stdout.flush()
sys.stderr.write(spec.get("stderr", ""))
sys.exit(spec.get("exit", 0))
"""


class FakeTool:
    """Handle on an installed fake executable."""

    def __init__(self, directory: Path, name: str) -> None:
        self.directory = directory
        self.name = name

    @property
    def calls(self) -> list[list[str]]:
        """Every argv (minus argv[0]) the fake was invoked with, oldest first."""
        path = self.directory / f"{self.name}.argv.json"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.fixture
def fake_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., FakeTool]:
    """Install a fake executable on PATH that prints canned output and records its argv.

    Each invocation prints the next entry of ``outputs`` (the last one repeats), writes
    ``stderr`` and exits with ``exit_code``.
    """
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    (bin_dir / "shim.py").write_text(SHIM, encoding="utf-8")
    monkeypatch.setenv("PATH", str(bin_dir) + os.pathsep + os.environ.get("PATH", ""))

    def install(name: str, *outputs: str, exit_code: int = 0, stderr: str = "") -> FakeTool:
        spec = {"outputs": list(outputs) or [""], "exit": exit_code, "stderr": stderr}
        (bin_dir / f"{name}.spec.json").write_text(json.dumps(spec), encoding="utf-8")
        python = sys.executable
        if os.name == "nt":
            launcher = bin_dir / f"{name}.cmd"
            launcher.write_text(
                f'@echo off\r\n"{python}" "%~dp0shim.py" {name} %*\r\n', encoding="utf-8"
            )
        else:
            launcher = bin_dir / name
            launcher.write_text(
                f'#!/bin/sh\nexec "{python}" "$(dirname "$0")/shim.py" {name} "$@"\n',
                encoding="utf-8",
            )
            launcher.chmod(launcher.stat().st_mode | stat.S_IEXEC)
        return FakeTool(bin_dir, name)

    return install
