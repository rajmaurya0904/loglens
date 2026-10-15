"""Log sources for loglens."""

from abc import ABC, abstractmethod
from collections.abc import Iterator


class LogSource(ABC):
    """Abstract base class for log sources."""

    @abstractmethod
    def stream(self) -> Iterator[tuple[float, str]]:
        """Yield (timestamp, line) tuples from the log source.

        Returns:
            An iterator of (timestamp, line) where timestamp is a float
            (seconds since epoch) and line is a string without trailing newline.
        """
        pass