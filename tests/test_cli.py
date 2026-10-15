"""Test that the CLI entry point exists and is callable."""

import loglens.__main__


def test_main_callable() -> None:
    """Assert that loglens.__main__.main is callable."""
    assert callable(loglens.__main__.main)