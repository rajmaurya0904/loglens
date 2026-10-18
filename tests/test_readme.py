"""Keep the README honest: the sample output blocks must be what loglens really prints."""

import io
import re
import shlex
from pathlib import Path

import pytest

from loglens.__main__ import main

ROOT = Path(__file__).resolve().parent.parent
BLOCK = re.compile(r"```console\n\$ (loglens [^\n]+)\n(.*?)```", re.DOTALL)


def readme_examples() -> list[tuple[str, str]]:
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    return [(command, output) for command, output in BLOCK.findall(text)]


def test_readme_has_example_blocks() -> None:
    assert len(readme_examples()) >= 2


@pytest.mark.parametrize(("command", "expected"), readme_examples())
def test_readme_output_matches_a_real_run(
    command: str, expected: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(ROOT)
    argv = shlex.split(command)[1:]
    out = io.StringIO()
    assert main(argv, stdout=out) == 0
    assert out.getvalue() == expected
