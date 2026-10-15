"""Smoke test: package imports cleanly. Replace/extend as modules land."""

import loglens


def test_version_is_set() -> None:
    assert loglens.__version__
