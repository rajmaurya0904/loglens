from unittest.mock import patch

import pytest

from loglens.sources import DockerComposeSource, KubernetesSource, LogLensError


def test_docker_compose_source_missing_command():
    with patch("loglens.sources.subprocess.Popen", side_effect=FileNotFoundError):
        source = DockerComposeSource()
        with pytest.raises(LogLensError, match="docker compose command not found"):
            # Consume the generator to trigger the exception
            list(source.stream())


def test_kubernetes_source_missing_command():
    with patch("loglens.sources.subprocess.Popen", side_effect=FileNotFoundError):
        source = KubernetesSource(pod_name="test-pod")
        with pytest.raises(LogLensError, match="kubectl command not found"):
            list(source.stream())