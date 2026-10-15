"""Tests for the loglens CLI entry point."""

import loglens.__main__


def test_build_parser() -> None:
    """Parser can be built and has expected arguments."""
    parser = loglens.__main__.build_parser()
    # Check that --services and --limit are present
    args = parser.parse_args(["--services", "svc1", "--limit", "10"])
    assert args.services == ["svc1"]
    assert args.limit == 10


def test_main_returns_zero() -> None:
    """Calling main with valid args returns exit code 0."""
    assert loglens.__main__.main(["--services", "svc1", "--limit", "10"]) == 0
    # Also test without arguments (should still return 0)
    assert loglens.__main__.main([]) == 0