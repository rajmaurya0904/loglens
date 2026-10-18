"""Tests for DockerComposeSource using a stand-in `docker` executable."""

import pytest

from loglens.sources import DockerComposeSource, Entry, LogLensError

BASE = 1704110400.0

COMPOSE_OUTPUT = (
    "web-1  | 2024-01-01T12:00:00.000000000Z listening on :8080\n"
    "db-1   | 2024-01-01T12:00:00.500000000Z ready to accept connections\n"
    "web-1  | 2024-01-01T12:00:01.000000000Z GET /health 200\n"
)


def test_parses_real_compose_prefix_and_strips_replica_suffix(fake_tool) -> None:
    fake_tool("docker", COMPOSE_OUTPUT)
    entries = list(DockerComposeSource().stream())
    assert entries == [
        Entry(BASE, "web", "listening on :8080"),
        Entry(BASE + 0.5, "db", "ready to accept connections"),
        Entry(BASE + 1.0, "web", "GET /health 200"),
    ]


def test_builds_expected_command(fake_tool) -> None:
    tool = fake_tool("docker", COMPOSE_OUTPUT)
    list(DockerComposeSource(["web", "db"], project="shop", tail=50).stream())
    assert tool.calls == [
        [
            "compose",
            "-p",
            "shop",
            "logs",
            "--timestamps",
            "--no-color",
            "-f",
            "--tail",
            "50",
            "web",
            "db",
        ]
    ]


def test_no_follow_and_compose_files(fake_tool) -> None:
    tool = fake_tool("docker", COMPOSE_OUTPUT)
    list(DockerComposeSource(compose_files=["a.yml", "b.yml"], follow=False).stream())
    assert tool.calls == [
        ["compose", "-f", "a.yml", "-f", "b.yml", "logs", "--timestamps", "--no-color"]
    ]


def test_drops_attach_banner_and_unprefixed_lines(fake_tool) -> None:
    fake_tool(
        "docker",
        "Attaching to web-1\nWARN[0000] something\nweb-1  | 2024-01-01T12:00:00Z hello\n",
    )
    assert [e.message for e in DockerComposeSource().stream()] == ["hello"]


def test_legacy_underscore_replica_names(fake_tool) -> None:
    fake_tool("docker", "api_2  | 2024-01-01T12:00:00Z up\n")
    assert next(DockerComposeSource().stream()).service == "api"


def test_service_names_with_dashes_are_kept(fake_tool) -> None:
    fake_tool("docker", "order-worker-1  | 2024-01-01T12:00:00Z up\n")
    assert next(DockerComposeSource().stream()).service == "order-worker"


def test_message_containing_pipe_is_preserved(fake_tool) -> None:
    fake_tool("docker", "web-1  | 2024-01-01T12:00:00Z a | b | c\n")
    assert next(DockerComposeSource().stream()).message == "a | b | c"


def test_since_is_passed_as_rfc3339(fake_tool) -> None:
    tool = fake_tool("docker", COMPOSE_OUTPUT)
    list(DockerComposeSource(since=BASE).stream())
    assert "2024-01-01T12:00:00.000000Z" in tool.calls[0]


def test_missing_docker_raises_loglens_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    source = DockerComposeSource()
    with pytest.raises(LogLensError, match="docker compose command not found"):
        source.check()
    with pytest.raises(LogLensError, match="docker compose command not found"):
        list(source.stream())


def test_failing_docker_reports_stderr(fake_tool) -> None:
    fake_tool("docker", "", exit_code=1, stderr="no configuration file provided: not found")
    with pytest.raises(LogLensError, match="no configuration file provided"):
        list(DockerComposeSource().stream())


def test_reconnect_resumes_with_since_and_dedupes(fake_tool) -> None:
    tool = fake_tool(
        "docker",
        "web-1  | 2024-01-01T12:00:00Z one\nweb-1  | 2024-01-01T12:00:01Z two\n",
        "web-1  | 2024-01-01T12:00:01Z two\nweb-1  | 2024-01-01T12:00:02Z three\n",
    )
    source = DockerComposeSource(reconnect=True, retry_delay=0.01)
    stream = source.stream()
    got = [next(stream).message for _ in range(3)]
    source.close()
    assert got == ["one", "two", "three"]
    assert "--since" not in tool.calls[0]
    assert tool.calls[1][tool.calls[1].index("--since") + 1] == "2024-01-01T12:00:01.000000Z"
