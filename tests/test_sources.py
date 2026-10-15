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