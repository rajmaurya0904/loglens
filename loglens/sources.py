"""Log sources for loglens."""

import subprocess
from abc import ABC, abstractmethod
from collections.abc import Iterator
from datetime import datetime


class LogSource(ABC):
    """Abstract base class for log sources."""
    @abstractmethod
    def stream(self) -> Iterator[tuple[float, str]]:
        """Yield (timestamp, line) tuples from the source."""


class DockerComposeSource(LogSource):
    """Stream logs from `docker compose logs -f --timestamps`."""

    def stream(self) -> Iterator[tuple[float, str]]:
        proc = subprocess.Popen(
            ["docker", "compose", "logs", "-f", "--timestamps"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                # Expected format: <service> | <timestamp> | <message>
                parts = line.split(" | ", 2)
                if len(parts) != 3:
                    # Skip malformed lines
                    continue
                _, timestamp_str, message = parts
                # Convert ISO 8601 timestamp to seconds since epoch.
                # Handle Zulu time suffix.
                if timestamp_str.endswith("Z"):
                    timestamp_str = timestamp_str[:-1] + "+00:00"
                dt = datetime.fromisoformat(timestamp_str)
                timestamp = dt.timestamp()
                yield (timestamp, message)
        finally:
            proc.wait()


class KubernetesSource(LogSource):
    """Stream logs from `kubectl logs -f --timestamps` for a given pod."""

    def __init__(self, pod_name: str, namespace: str | None = None) -> None:
        self.pod_name = pod_name
        self.namespace = namespace

    def stream(self) -> Iterator[tuple[float, str]]:
        cmd = ["kubectl", "logs", "-f", "--timestamps"]
        if self.namespace:
            cmd.extend(["-n", self.namespace])
        cmd.append(self.pod_name)

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            for line in proc.stdout:
                line = line.rstrip("\n")
                # Expected format: <timestamp> <message>
                parts = line.split(" ", 1)
                if len(parts) != 2:
                    # Skip malformed lines
                    continue
                timestamp_str, message = parts
                # Convert ISO 8601 timestamp to seconds since epoch.
                # Handle Zulu time suffix.
                if timestamp_str.endswith("Z"):
                    timestamp_str = timestamp_str[:-1] + "+00:00"
                dt = datetime.fromisoformat(timestamp_str)
                timestamp = dt.timestamp()
                yield (timestamp, message)
        finally:
            proc.wait()