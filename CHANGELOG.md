# Changelog

## [0.1.0] - 2026-10-18

### Added
- Sources: `docker compose logs`, `kubectl logs` (single pods or label selectors), plain
  files (optionally followed), standard input and arbitrary commands.
- Time-ordered merge of all sources, with a small hold-back window so slow or quiet sources
  do not break ordering of live streams.
- RFC 3339 timestamp parsing including nanoseconds, numeric offsets, `UTC` suffixes, epoch
  values and JSON `time` / `ts` / `timestamp` fields. Lines without a timestamp (stack
  traces) stay attached to the line before them.
- Per-service colours that are stable across runs, red and yellow highlighting for error and
  warning lines, aligned columns, `--json` output.
- Filtering by service (globs), regex, severity and age; `--limit`, `--tail`, `--since`.
- `--reconnect` to re-attach after a container restart or pod reschedule without repeating
  lines.
- Clear errors and exit code 2 when `docker`, `kubectl` or a file is missing.
