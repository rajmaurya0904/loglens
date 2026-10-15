"""Tests for DockerComposeSource with mocked subprocess."""

import subprocess
from itertools import islice
from unittest.mock import MagicMock, patch

from loglens.sources import DockerComposeSource


def test_docker_compose_source_stream_two_lines() -> None:
    """DockerComposeSource.stream yields two (timestamp, line) tuples from mocked subprocess."""
    line1 = "service1 | 2024-01-01T12:00:00Z | message one"
    line2 = "service2 | 2024-01-01T12:00:01Z | message two"
    mock_proc = MagicMock()
    mock_proc.stdout = [line1 + "\n", line2 + "\n"]
    mock_proc.wait = MagicMock()

    with patch("loglens.sources.subprocess.Popen", return_value=mock_proc) as mock_popen:
        source = DockerComposeSource()
        result = list(islice(source.stream(), 2))
        assert len(result) == 2
        # First line
        timestamp1, msg1 = result[0]
        assert isinstance(timestamp1, float)
        assert isinstance(msg1, str)
        assert msg1 == "message one"
        # Second line
        timestamp2, msg2 = result[1]
        assert isinstance(timestamp2, float)
        assert isinstance(msg2, str)
        assert msg2 == "message two"
        # Timestamps should be one second apart
        assert abs(timestamp2 - timestamp1 - 1.0) < 0.001
        mock_popen.assert_called_once_with(
            ["docker", "compose", "logs", "-f", "--timestamps"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        mock_proc.wait.assert_called_once()