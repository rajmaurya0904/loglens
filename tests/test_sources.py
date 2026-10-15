"""Tests for loglens.sources."""

import inspect
import subprocess
from itertools import islice
from unittest.mock import MagicMock, patch

from loglens.sources import DockerComposeSource, KubernetesSource, LogSource


def test_log_source_is_abstract_base_class() -> None:
    """LogSource should be an abstract base class."""
    assert inspect.isabstract(LogSource) is True


def test_docker_compose_source_stream_yields_tuple() -> None:
    """DockerComposeSource.stream should yield (timestamp, line) tuples."""
    sample_line = "service | 2024-01-01T12:00:00Z | hello world"
    mock_proc = MagicMock()
    mock_proc.stdout = [sample_line + "\n"]
    mock_proc.wait = MagicMock()

    with patch("loglens.sources.subprocess.Popen", return_value=mock_proc) as mock_popen:
        source = DockerComposeSource()
        result = list(islice(source.stream(), 1))
        assert len(result) == 1
        timestamp, line = result[0]
        assert isinstance(timestamp, float)
        assert isinstance(line, str)
        assert line == "hello world"
        mock_popen.assert_called_once_with(
            ["docker", "compose", "logs", "-f", "--timestamps"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )


def test_kubernetes_source_stream_yields_tuple() -> None:
    """KubernetesSource.stream should yield (timestamp, line) tuples."""
    sample_line = "2024-01-01T12:00:00Z hello world"
    mock_proc = MagicMock()
    mock_proc.stdout = [sample_line + "\n"]
    mock_proc.wait = MagicMock()

    with patch("loglens.sources.subprocess.Popen", return_value=mock_proc) as mock_popen:
        source = KubernetesSource(pod_name="test-pod")
        result = list(islice(source.stream(), 1))
        assert len(result) == 1
        timestamp, line = result[0]
        assert isinstance(timestamp, float)
        assert isinstance(line, str)
        assert line == "hello world"
        mock_popen.assert_called_once_with(
            ["kubectl", "logs", "-f", "--timestamps", "test-pod"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )


def test_kubernetes_source_with_namespace() -> None:
    """KubernetesSource should include namespace when provided."""
    sample_line = "2024-01-01T12:00:00Z hello world"
    mock_proc = MagicMock()
    mock_proc.stdout = [sample_line + "\n"]
    mock_proc.wait = MagicMock()

    with patch("loglens.sources.subprocess.Popen", return_value=mock_proc) as mock_popen:
        source = KubernetesSource(pod_name="test-pod", namespace="test-ns")
        # Consume one item to trigger the Popen call
        list(islice(source.stream(), 1))
        mock_popen.assert_called_once_with(
            ["kubectl", "logs", "-f", "--timestamps", "-n", "test-ns", "test-pod"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )