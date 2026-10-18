"""Tests for KubernetesSource using a stand-in `kubectl` executable."""

import pytest

from loglens.sources import Entry, KubernetesSource, LogLensError

BASE = 1704110400.0


def test_single_pod_stream(fake_tool) -> None:
    fake_tool(
        "kubectl",
        "2024-01-01T12:00:00.123456789Z log line one\n2024-01-01T12:00:01Z log line two\n",
    )
    entries = list(KubernetesSource("api-7d9", "prod").stream())
    assert entries == [
        Entry(BASE + 0.123456, "api-7d9", "log line one"),
        Entry(BASE + 1, "api-7d9", "log line two"),
    ]


def test_builds_expected_command(fake_tool) -> None:
    tool = fake_tool("kubectl", "")
    list(
        KubernetesSource(
            "api-7d9", "prod", container="app", context="staging", tail=20, since=BASE
        ).stream()
    )
    assert tool.calls == [
        [
            "--context",
            "staging",
            "logs",
            "-f",
            "--timestamps",
            "-n",
            "prod",
            "-c",
            "app",
            "--tail",
            "20",
            "--since-time",
            "2024-01-01T12:00:00.000000Z",
            "api-7d9",
        ]
    ]


def test_no_follow_omits_f_flag(fake_tool) -> None:
    tool = fake_tool("kubectl", "")
    list(KubernetesSource("p", follow=False).stream())
    assert tool.calls == [["logs", "--timestamps", "p"]]


def test_selector_mode_parses_pod_prefix(fake_tool) -> None:
    tool = fake_tool(
        "kubectl",
        "[pod/api-1/app] 2024-01-01T12:00:00Z hello\n"
        "[pod/api-2/app] 2024-01-01T12:00:00.5Z world\n"
        "error: something odd\n",
    )
    entries = list(KubernetesSource(selector="app=api", follow=False).stream())
    assert entries == [Entry(BASE, "api-1", "hello"), Entry(BASE + 0.5, "api-2", "world")]
    assert tool.calls == [["logs", "--timestamps", "-l", "app=api", "--prefix"]]


def test_requires_pod_or_selector() -> None:
    with pytest.raises(LogLensError, match="pod name or a label selector"):
        KubernetesSource()


def test_missing_kubectl_raises_loglens_error(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    source = KubernetesSource("p")
    with pytest.raises(LogLensError, match="kubectl command not found"):
        source.check()
    with pytest.raises(LogLensError, match="kubectl command not found"):
        list(source.stream())


def test_pod_not_found_surfaces_kubectl_error(fake_tool) -> None:
    fake_tool("kubectl", "", exit_code=1, stderr="Error from server (NotFound): pod not found")
    with pytest.raises(LogLensError, match="NotFound"):
        list(KubernetesSource("x").stream())
