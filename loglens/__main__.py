"""Command-line entry point for loglens."""

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the loglens CLI."""
    parser = argparse.ArgumentParser(
        prog="loglens",
        description="Aggregate and colorize logs from multiple services.",
    )
    parser.add_argument(
        "--services",
        action="append",
        default=None,
        metavar="SERVICE",
        help="Service to include (repeatable).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        metavar="N",
        help="Maximum number of log lines to show.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse CLI arguments and run loglens.

    Returns the process exit code.
    """
    parser = build_parser()
    parser.parse_args(argv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())