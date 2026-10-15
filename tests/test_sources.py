"""Tests for loglens.sources."""

import inspect

import pytest

from loglens.sources import LogSource


def test_log_source_is_abstract_base_class() -> None:
    """LogSource should be an abstract base class with stream method."""
    assert inspect.isabstract(LogSource)
    # Check that stream is an abstract method
    assert "stream" in LogSource.__abstractmethods__


def test_log_source_cannot_be_instantiated() -> None:
    """Instantiating LogSource directly should raise TypeError."""
    with pytest.raises(TypeError):
        LogSource()  # type: ignore[abstract]


def test_log_source_subclass_stream_can_be_called() -> None:
    """Define a dummy subclass of LogSource and verify stream() can be called."""
    class DummyLogSource(LogSource):
        def stream(self):
            # Return an empty iterator
            return iter([])

    # Instantiate the dummy subclass
    source = DummyLogSource()
    # Call stream and verify it returns an iterator
    it = source.stream()
    # We can call next() and expect StopIteration because it's empty
    with pytest.raises(StopIteration):
        next(it)