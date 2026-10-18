"""Command-line entry point for loglens."""

from __future__ import annotations

import argparse
import os
import re
import shlex
import sys
import time
from collections.abc import Sequence
from typing import IO

from loglens import __version__
from loglens.filters import LEVELS, EntryFilter
from loglens.merge import LiveMerger
from loglens.render import Formatter
from loglens.sources import (
    CommandSource,
    DockerComposeSource,
    FileSource,
    KubernetesSource,
    LogLensError,
    LogSource,
    StdinSource,
)
from loglens.timestamps import parse_since

_NAMED = re.compile(r"^(?P<name>[A-Za-z0-9_.\-]{2,})=(?P<value>.+)$")


def _non_negative(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid integer: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return value


def _non_negative_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid number: {text!r}") from None
    if value < 0:
        raise argparse.ArgumentTypeError("must be 0 or greater")
    return value


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the loglens CLI."""
    parser = argparse.ArgumentParser(
        prog="loglens",
        description=(
            "Merge logs from docker compose, Kubernetes pods, files and commands into one "
            "time-ordered, colour-coded stream. With no source options it reads "
            "`docker compose logs` for the project in the current directory."
        ),
        epilog=(
            "examples:\n"
            "  loglens --services web --services db --limit 200\n"
            "  loglens --k8s api-7d9 --k8s worker-5f2 -n prod --grep timeout\n"
            "  loglens --file api=/var/log/api.log --file db=/var/log/db.log --no-follow\n"
            "  loglens --cmd 'edge=ssh edge1 journalctl -f -o short-iso' --level warn\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-V", "--version", action="version", version=f"loglens {__version__}")

    src = parser.add_argument_group("sources")
    src.add_argument(
        "--compose",
        action="store_true",
        help="read docker compose logs (the default when no other source is given)",
    )
    src.add_argument(
        "--services",
        action="append",
        default=None,
        metavar="SERVICE",
        help="compose service to stream (repeatable; default: all services)",
    )
    src.add_argument(
        "--compose-file",
        action="append",
        default=None,
        metavar="FILE",
        help="compose file to use (repeatable)",
    )
    src.add_argument("--project-name", metavar="NAME", help="compose project name")
    src.add_argument(
        "--k8s",
        action="append",
        default=None,
        metavar="POD",
        help="Kubernetes pod to stream (repeatable)",
    )
    src.add_argument(
        "-l",
        "--selector",
        action="append",
        default=None,
        metavar="LABELS",
        help="Kubernetes label selector, e.g. app=api (repeatable)",
    )
    src.add_argument("-n", "--namespace", metavar="NS", help="Kubernetes namespace")
    src.add_argument("-c", "--container", metavar="NAME", help="container within the pod(s)")
    src.add_argument("--context", metavar="CTX", help="kubectl context")
    src.add_argument(
        "--file",
        action="append",
        default=None,
        metavar="[NAME=]PATH",
        help="log file to read (repeatable); NAME labels it, `-` reads standard input",
    )
    src.add_argument(
        "--cmd",
        action="append",
        default=None,
        metavar="NAME=COMMAND",
        help="run COMMAND and use its output as log lines (repeatable)",
    )

    beh = parser.add_argument_group("behaviour")
    beh.add_argument(
        "--no-follow",
        dest="follow",
        action="store_false",
        help="print what is there and exit instead of streaming",
    )
    beh.add_argument(
        "--tail", type=_non_negative, metavar="N", help="start from the last N lines of each source"
    )
    beh.add_argument(
        "--since",
        metavar="TIME",
        help="drop lines older than TIME: a duration (10m, 2h) or an ISO timestamp",
    )
    beh.add_argument(
        "--reconnect",
        action="store_true",
        help="re-attach when a stream ends (container restart, pod reschedule)",
    )
    beh.add_argument(
        "--window",
        type=_non_negative_float,
        default=0.5,
        metavar="SECONDS",
        help="how long to hold a line waiting for older ones from quiet sources (default: 0.5)",
    )

    flt = parser.add_argument_group("filtering")
    flt.add_argument(
        "--filter",
        action="append",
        default=None,
        metavar="SERVICE",
        help="only show these services (repeatable, globs allowed)",
    )
    flt.add_argument(
        "--exclude",
        action="append",
        default=None,
        metavar="SERVICE",
        help="hide these services (repeatable, globs allowed)",
    )
    flt.add_argument("--grep", metavar="REGEX", help="only show lines matching REGEX")
    flt.add_argument("--grep-v", metavar="REGEX", help="hide lines matching REGEX")
    flt.add_argument("-i", "--ignore-case", action="store_true", help="case-insensitive grep")
    flt.add_argument(
        "--level",
        choices=sorted(LEVELS, key=LEVELS.get),  # type: ignore[arg-type]
        metavar="LEVEL",
        help="hide lines below this severity (trace, debug, info, warn, error, fatal)",
    )
    flt.add_argument(
        "--limit",
        type=_non_negative,
        default=None,
        metavar="N",
        help="stop after printing N lines",
    )

    out = parser.add_argument_group("output")
    out.add_argument(
        "--color",
        choices=("auto", "always", "never"),
        default="auto",
        help="colourise output (default: auto, on for terminals)",
    )
    out.add_argument("--no-time", dest="show_time", action="store_false", help="hide timestamps")
    out.add_argument(
        "--json", dest="json_lines", action="store_true", help="print one JSON object per line"
    )
    return parser


def split_command(text: str) -> list[str]:
    """Split a command string into argv, keeping Windows backslashes intact."""
    try:
        if os.name == "nt":
            parts = shlex.split(text, posix=False)
            return [p[1:-1] if len(p) > 1 and p[0] == p[-1] and p[0] in "'\"" else p for p in parts]
        return shlex.split(text)
    except ValueError as exc:
        raise LogLensError(f"cannot parse command {text!r}: {exc}") from exc


def build_sources(args: argparse.Namespace, stdin: IO[str] | None = None) -> list[LogSource]:
    """Create the sources requested on the command line."""
    follow: bool = args.follow
    since = args.since_epoch
    tail = args.tail
    reconnect = args.reconnect and follow
    sources: list[LogSource] = []

    for pod in args.k8s or []:
        sources.append(
            KubernetesSource(
                pod,
                args.namespace,
                container=args.container,
                context=args.context,
                follow=follow,
                tail=tail,
                since=since,
                reconnect=reconnect,
            )
        )
    for selector in args.selector or []:
        sources.append(
            KubernetesSource(
                selector=selector,
                namespace=args.namespace,
                container=args.container,
                context=args.context,
                follow=follow,
                tail=tail,
                since=since,
                reconnect=reconnect,
            )
        )
    for spec in args.file or []:
        match = _NAMED.match(spec)
        name, path = (match["name"], match["value"]) if match else (None, spec)
        if path == "-":
            sources.append(StdinSource(name or "stdin", stdin))
        else:
            sources.append(FileSource(path, name, follow=follow, tail=tail))
    for spec in args.cmd or []:
        match = _NAMED.match(spec)
        if not match:
            raise LogLensError(f"--cmd expects NAME=COMMAND, got {spec!r}")
        sources.append(
            CommandSource(match["name"], split_command(match["value"]), reconnect=reconnect)
        )

    wants_compose = (
        args.compose
        or args.services
        or args.compose_file
        or args.project_name
        or not sources
    )
    if wants_compose:
        sources.insert(
            0,
            DockerComposeSource(
                args.services or [],
                compose_files=args.compose_file or [],
                project=args.project_name,
                follow=follow,
                tail=tail,
                since=since,
                reconnect=reconnect,
            ),
        )
    return sources


def wants_color(mode: str, stream: IO[str]) -> bool:
    """Decide whether to emit ANSI colour for ``stream``."""
    if mode == "always":
        return True
    if mode == "never":
        return False
    if os.environ.get("NO_COLOR") or os.environ.get("TERM") == "dumb":
        return False
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


def _enable_windows_ansi() -> None:
    if sys.platform == "win32":
        os.system("")  # flips the console into VT mode as a side effect


def _known_names(args: argparse.Namespace, sources: Sequence[LogSource]) -> list[str]:
    """Service labels that are known before any output arrives (for column alignment)."""
    names = list(args.services or [])
    for source in sources:
        if isinstance(source, DockerComposeSource) or getattr(source, "selector", None):
            continue
        names.append(source.name)
    return names


def run(
    args: argparse.Namespace, out: IO[str], stdin: IO[str] | None = None, now: float | None = None
) -> int:
    """Run loglens with parsed arguments, writing merged lines to ``out``."""
    current = time.time() if now is None else now
    args.since_epoch = None
    if args.since:
        try:
            args.since_epoch = parse_since(args.since, current)
        except ValueError as exc:
            raise LogLensError(str(exc)) from exc

    sources = build_sources(args, stdin)
    entry_filter = EntryFilter(
        args.filter or [],
        args.exclude or [],
        grep=args.grep,
        ignore_case=args.ignore_case,
        min_level=args.level,
        since=args.since_epoch,
    )
    exclusion = EntryFilter(grep=args.grep_v, ignore_case=args.ignore_case, invert_grep=True)
    use_color = wants_color(args.color, out)
    if use_color:
        _enable_windows_ansi()
    known = [len(name) for name in _known_names(args, sources)]
    formatter = Formatter(
        color=use_color,
        show_time=args.show_time,
        json_lines=args.json_lines,
        width=max(known, default=0),
    )

    merger = LiveMerger(sources, window=args.window)
    if args.limit == 0:
        for source in sources:
            source.check()
        return 0
    printed = 0
    try:
        for entry in merger:
            if not entry_filter(entry):
                continue
            if args.grep_v is not None and not exclusion(entry):
                continue
            out.write(formatter.format(entry) + "\n")
            out.flush()
            printed += 1
            if args.limit is not None and printed >= args.limit:
                break
    finally:
        merger.close()
    return 0


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: IO[str] | None = None,
    stdin: IO[str] | None = None,
) -> int:
    """Parse CLI arguments and run loglens.

    Returns the process exit code: 0 on success, 2 for usage errors and unusable sources,
    130 when interrupted.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    out = stdout if stdout is not None else sys.stdout
    if stdout is None and hasattr(out, "reconfigure"):
        out.reconfigure(encoding="utf-8", errors="replace")
    if stdin is None and hasattr(sys.stdin, "reconfigure"):
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    try:
        return run(args, out, stdin)
    except LogLensError as exc:
        print(f"loglens: error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130
    except BrokenPipeError:
        if stdout is None:  # downstream (e.g. `head`) closed the pipe: not an error
            try:
                os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
            except (OSError, ValueError):
                pass
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
