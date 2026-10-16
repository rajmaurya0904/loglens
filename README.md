# Loglens

**A CLI tool that aggregates and colorizes logs from multiple services (docker compose, k8s) in real-time, for developers debugging microservices.**

Loglens solves the problem of scattered logs in microservices, making it hard to correlate events across services.

Loglens addresses the pain of chasing logs across multiple services.

In a microservices architecture, logs are often spread across many containers, pods, or services. Developers must switch contexts, run multiple commands, and manually correlate timestamps, which is error‑prone and time‑consuming.

Switching between `kubectl logs` and `docker compose logs` is tedious. Missing context when incidents span services. Hard to correlate events across containers.

## Example

```bash
$ python -m loglens --help
usage: loglens [-h] [--services SERVICE] [--limit N]

Aggregate and colorize logs from multiple services.

options:
  -h, --help          show this help message and exit
  --services SERVICE  Service to include (repeatable).
  --limit N           Maximum number of log lines to show.
```

## Install

```bash
pip install -e ".[dev]"
```

## Usage

- Aggregate logs from all services: `python -m loglens`
- Filter to specific services: `python -m loglens --services web --services db`
- Limit the number of lines: `python -m loglens --limit 500`

## How it works

- **Source abstraction:** `loglens` defines a common `LogSource` interface that wraps both Docker Compose (`docker compose logs -f`) and Kubernetes (`kubectl logs -f`) back‑ends, exposing a unified iterator of log lines.
- **Merging:** Log lines from all active sources are merged in chronological order using a priority queue, so events from different services appear interleaved correctly as they happen.
- **Timestamping:** Each line is prefixed with a UTC timestamp generated at receipt, ensuring a consistent ordering across sources.
- **Colorization:** A deterministic colour is assigned per service name; the formatter injects ANSI colour codes so each service’s output is visually distinct.
- **Resilience:** The merger watches for source termination (e.g., container restart or pod reschedule) and automatically re‑attaches, keeping the stream continuous.

## Limitations

- Does not persist logs; only shows live streams
- Requires `kubectl` to be configured and accessible in PATH for Kubernetes logs
- Does not support multi-line log parsing (e.g., stack traces)
- Tested primarily with Linux and macOS

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

## License

MIT -- see [LICENSE](LICENSE).