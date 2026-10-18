"""Tests for the filtering flags: --filter, --exclude, --grep, --grep-v, --level."""

from pathlib import Path

import pytest

from tests.helpers import run_cli, write_logs


def services(lines: list[str]) -> set[str]:
    return {line.split("|")[0].strip() for line in lines}


@pytest.fixture
def files(tmp_path: Path) -> list[str]:
    api, payments = write_logs(tmp_path)
    return ["--no-follow", "--file", str(api), "--file", str(payments)]


def test_filter_keeps_only_the_named_service(files: list[str]) -> None:
    code, lines = run_cli(*files, "--filter", "payments")
    assert code == 0
    assert services(lines) == {"payments"}
    assert len(lines) == 4


def test_filter_is_repeatable_and_accepts_globs(files: list[str]) -> None:
    _, lines = run_cli(*files, "--filter", "pay*", "--filter", "api")
    assert services(lines) == {"payments", "api"}
    _, lines = run_cli(*files, "--filter", "a?i")
    assert services(lines) == {"api"}


def test_filter_for_unknown_service_prints_nothing(files: list[str]) -> None:
    code, lines = run_cli(*files, "--filter", "ghost")
    assert code == 0 and lines == []


def test_exclude_hides_a_service(files: list[str]) -> None:
    _, lines = run_cli(*files, "--exclude", "api")
    assert services(lines) == {"payments"}


def test_grep_selects_matching_lines(files: list[str]) -> None:
    _, lines = run_cli(*files, "--grep", "order=42|502")
    assert len(lines) == 2
    assert any("charge order=42" in line for line in lines)
    assert any("POST /orders 502" in line for line in lines)


def test_grep_ignore_case(files: list[str]) -> None:
    _, strict = run_cli(*files, "--grep", "TIMEOUT")
    _, loose = run_cli(*files, "--grep", "TIMEOUT", "-i")
    assert strict == []
    assert len(loose) == 1 and "read timeout" in loose[0]


def test_grep_v_hides_matching_lines(files: list[str]) -> None:
    _, everything = run_cli(*files)
    _, lines = run_cli(*files, "--grep-v", "health|worker ready")
    assert len(lines) == len(everything) - 2
    assert not any("health" in line for line in lines)


def test_grep_and_grep_v_combine(files: list[str]) -> None:
    _, lines = run_cli(*files, "--grep", "ERROR", "--grep-v", "stripe")
    assert len(lines) == 1 and "POST /orders 502" in lines[0]


def test_invalid_regex_exits_2(files: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = run_cli(*files, "--grep", "(oops")
    assert code == 2
    assert "invalid --grep pattern" in capsys.readouterr().err


def test_level_warn_hides_info_but_keeps_trace_lines_of_errors(files: list[str]) -> None:
    code, lines = run_cli(*files, "--level", "warn")
    assert code == 0
    text = "\n".join(lines)
    assert "INFO" not in text
    assert "WARN slow upstream" in text and "ERROR POST /orders 502" in text
    # the stack trace belongs to the ERROR line, so it stays
    assert "Traceback" in text and "ConnectionResetError" in text


def test_level_error_is_stricter(files: list[str]) -> None:
    _, lines = run_cli(*files, "--level", "error")
    assert not any("WARN" in line for line in lines)
    assert any("stripe" in line for line in lines)


def test_unknown_level_is_rejected_by_the_parser(
    files: list[str], capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as exc:
        run_cli(*files, "--level", "loud")
    assert exc.value.code == 2
    assert "invalid choice" in capsys.readouterr().err


def test_filters_combine(files: list[str]) -> None:
    _, lines = run_cli(*files, "--filter", "api", "--level", "error", "--grep", "502")
    assert len(lines) == 1 and lines[0].startswith("api")
