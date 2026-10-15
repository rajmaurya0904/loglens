"""Tests for KubernetesSource with mocked subprocess."""

import subprocess
from itertools import islice
from unittest.mock import MagicMock, patch

from loglens.sources import KubernetesSource


@patch("loglens.sources.subprocess.Popen")
def test_kubernetes_source_stream(mock_popen):
    # Simulate kubectl output lines (timestamp and message)
    output_lines = [
        "2024-01-01T12:00:00Z log line one\n",
        "2024-01-01T12:00:01Z log line two\n",
    ]
    # Create a mock process
    mock_proc = MagicMock()
    mock_proc.stdout = output_lines
    mock_proc.wait = MagicMock()
    mock_popen.return_value = mock_proc

    source = KubernetesSource(pod_name="test-pod", namespace="default")
    # Take first two entries from the stream
    entries = list(islice(source.stream(), 2))

    # Verify Popen was called with correct arguments
    mock_popen.assert_called_once_with(
        ["kubectl", "logs", "-f", "--timestamps", "-n", "default", "test-pod"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    # Verify the parsed entries
    assert entries[0][1] == "log line one"
    assert entries[1][1] == "log line two"
    # Timestamps should be close to the mocked times (allow small difference)
    assert abs(entries[0][0] - 1704110400.0) < 1  # 2024-01-01T12:00:00Z
    assert abs(entries[1][0] - 1704110401.0) < 1  # 2024-01-01T12:00:01Z


@patch("loglens.sources.subprocess.Popen")
def test_kubernetes_source_stream_no_namespace(mock_popen):
    output_lines = [
        "2024-01-01T12:00:00Z solo line\n",
    ]
    mock_proc = MagicMock()
    mock_proc.stdout = output_lines
    mock_proc.wait = MagicMock()
    mock_popen.return_value = mock_proc

    source = KubernetesSource(pod_name="solo")
    entries = list(source.stream())

    mock_popen.assert_called_once_with(
        ["kubectl", "logs", "-f", "--timestamps", "solo"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    assert entries[0][1] == "solo line"
    assert abs(entries[0][0] - 1704110400.0) < 1