"""Tests for the loglens command line: parsing, sources, output and errors."""

import json
import sys
from pathlib import Path

import pytest

import loglens.__main__ as cli
from loglens import __version__
from tests.helpers import run_cli, write_logs


def test_main_is_callable() -> None:
    assert callable(cli.main)


def test_help_lists_every_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--help"])
    assert exc.value.code == 0
    text = capsys.readouterr().out
    for flag in ("--services", "--filter", "--limit", "--k8s", "--file", "--cmd", "--level"):
        assert flag in text


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_parser_accepts_repeatable_flags() -> None:
    args = cli.build_parser().parse_args(
        ["--services", "web", "--services", "db", "--filter", "web", "--limit", "10"]
    )
    assert args.services == ["web", "db"]
    assert args.filter == ["web"]
    assert args.limit == 10
    assert args.follow is True


@pytest.mark.parametrize("argv", [["--limit", "-1"], ["--tail", "x"], ["--window", "-2"]])
def test_parser_rejects_bad_numbers(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 2
    assert "error" in capsys.readouterr().err


def test_merges_two_files_chronologically(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    code, lines = run_cli(
        "--no-follow", "--color", "never", "--file", str(api), "--file", str(payments)
    )
    assert code == 0
    stamps = [line.split("|")[1].split()[0] for line in lines]
    assert stamps == sorted(stamps)
    assert lines[0].startswith("payments | 09:15:01.950")
    assert lines[1].startswith("api      | 09:15:02.104")
    assert len(lines) == 12


def test_named_files_and_service_labels(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    code, lines = run_cli(
        "--no-follow", "--file", f"gateway={api}", "--file", f"billing={payments}"
    )
    assert code == 0
    services = {line.split("|")[0].strip() for line in lines}
    assert services == {"gateway", "billing"}


def test_stack_trace_stays_attached_to_its_error_line(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    _, lines = run_cli("--no-follow", "--file", str(api), "--file", str(payments))
    index = next(i for i, line in enumerate(lines) if "POST /orders 502" in line)
    assert "Traceback" in lines[index + 1]
    assert "File \"api/handlers.py\"" in lines[index + 2]
    assert "ConnectionResetError" in lines[index + 3]


def test_stdin_source(tmp_path: Path) -> None:
    code, lines = run_cli(
        "--no-follow",
        "--file",
        "web=-",
        stdin="2024-05-14T09:15:00Z hello from a pipe\n2024-05-14T09:15:01Z bye\n",
    )
    assert code == 0
    assert lines == ["web | 09:15:00.000 hello from a pipe", "web | 09:15:01.000 bye"]


def test_no_time_hides_timestamps(tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    _, lines = run_cli("--no-follow", "--no-time", "--file", str(api), "--limit", "1")
    assert lines == ["api | INFO listening on :8080"]


def test_json_output(tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    _, lines = run_cli("--no-follow", "--json", "--file", str(api), "--limit", "2")
    records = [json.loads(line) for line in lines]
    assert records[0] == {
        "time": "2024-05-14T09:15:02.104000Z",
        "service": "api",
        "message": "INFO listening on :8080",
    }
    assert len(records) == 2


def test_color_always_and_never(tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    _, colored = run_cli("--no-follow", "--color", "always", "--file", str(api))
    _, plain = run_cli("--no-follow", "--color", "never", "--file", str(api))
    assert all("\x1b[" in line for line in colored)
    assert not any("\x1b" in line for line in plain)


def test_color_auto_is_off_when_not_a_terminal(tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    _, lines = run_cli("--no-follow", "--file", str(api))
    assert not any("\x1b" in line for line in lines)


def test_tail_limits_lines_per_source(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    _, lines = run_cli("--no-follow", "--tail", "1", "--file", str(api), "--file", str(payments))
    assert len(lines) == 2


def test_since_duration_and_timestamp(tmp_path: Path) -> None:
    api, payments = write_logs(tmp_path)
    _, lines = run_cli(
        "--no-follow",
        "--since",
        "2024-05-14T09:15:05Z",
        "--file",
        str(api),
        "--file",
        str(payments),
    )
    assert [line.split("|")[0].strip() for line in lines] == ["payments", "api"]
    code, lines = run_cli("--no-follow", "--since", "5m", "--file", str(api))
    assert code == 0 and lines == []  # 2024 is more than five minutes ago


def test_missing_file_exits_2_with_message(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, lines = run_cli("--no-follow", "--file", str(tmp_path / "nope.log"))
    assert code == 2
    assert lines == []
    assert "loglens: error: log file not found" in capsys.readouterr().err


def test_missing_docker_exits_2_with_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    code, _ = run_cli()
    assert code == 2
    assert "docker compose command not found" in capsys.readouterr().err


def test_missing_kubectl_exits_2_with_message(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    code, _ = run_cli("--k8s", "api-1")
    assert code == 2
    assert "kubectl command not found" in capsys.readouterr().err


def test_bad_since_exits_2(capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
    api, _ = write_logs(tmp_path)
    code, _ = run_cli("--no-follow", "--since", "whenever", "--file", str(api))
    assert code == 2
    assert "invalid time" in capsys.readouterr().err


def test_default_source_is_docker_compose(fake_tool) -> None:
    tool = fake_tool(
        "docker",
        "web-1  | 2024-05-14T09:15:00Z up\ndb-1   | 2024-05-14T09:15:01Z ready\n",
    )
    code, lines = run_cli("--no-follow")
    assert code == 0
    assert lines == ["web | 09:15:00.000 up", "db  | 09:15:01.000 ready"]
    assert tool.calls == [["compose", "logs", "--timestamps", "--no-color"]]


def test_services_flag_selects_compose_services(fake_tool) -> None:
    tool = fake_tool("docker", "web-1  | 2024-05-14T09:15:00Z up\n")
    code, lines = run_cli("--services", "web", "--no-follow", "--project-name", "shop")
    assert code == 0 and len(lines) == 1
    assert tool.calls[0] == ["compose", "-p", "shop", "logs", "--timestamps", "--no-color", "web"]


def test_compose_and_kubernetes_merge_together(fake_tool) -> None:
    fake_tool("docker", "web-1  | 2024-05-14T09:15:00Z compose first\n")
    fake_tool("kubectl", "2024-05-14T09:15:00.5Z pod second\n")
    code, lines = run_cli("--compose", "--k8s", "api-7d9", "-n", "prod", "--no-follow")
    assert code == 0
    assert [line.split("|")[0].strip() for line in lines] == ["web", "api-7d9"]


def test_kubernetes_selector_flag(fake_tool) -> None:
    tool = fake_tool("kubectl", "[pod/api-1/app] 2024-05-14T09:15:00Z hi\n")
    code, lines = run_cli("-l", "app=api", "-n", "prod", "-c", "app", "--no-follow")
    assert code == 0 and lines[0].startswith("api-1")
    assert tool.calls == [
        ["logs", "--timestamps", "-n", "prod", "-c", "app", "-l", "app=api", "--prefix"]
    ]


def test_cmd_source_runs_a_real_command() -> None:
    script = "print('2024-05-14T09:15:00Z from a command')"
    command = f'"{sys.executable}" -c "{script}"'
    code, lines = run_cli("--no-follow", "--cmd", f"job={command}")
    assert code == 0
    assert lines == ["job | 09:15:00.000 from a command"]


def test_cmd_requires_a_name(capsys: pytest.CaptureFixture[str]) -> None:
    code, _ = run_cli("--cmd", "just-a-command")
    assert code == 2
    assert "NAME=COMMAND" in capsys.readouterr().err


def test_split_command_handles_quotes_and_paths() -> None:
    assert cli.split_command('ssh host "journalctl -f"') == ["ssh", "host", "journalctl -f"]
    assert cli.split_command("echo a  b") == ["echo", "a", "b"]
    with pytest.raises(cli.LogLensError, match="cannot parse"):
        cli.split_command('echo "unterminated')


def test_wants_color_modes(monkeypatch: pytest.MonkeyPatch) -> None:
    class Tty:
        def isatty(self) -> bool:
            return True

    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm")
    assert cli.wants_color("always", object())  # type: ignore[arg-type]
    assert not cli.wants_color("never", Tty())  # type: ignore[arg-type]
    assert cli.wants_color("auto", Tty())  # type: ignore[arg-type]
    monkeypatch.setenv("NO_COLOR", "1")
    assert not cli.wants_color("auto", Tty())  # type: ignore[arg-type]
