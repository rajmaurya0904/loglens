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

- Tails log files from docker compose services via `docker compose logs -f`
- Tails logs from Kubernetes pods via `kubectl logs -f`
- Adds timestamps to each log line
- Colorizes output by service for easy visual parsing
- Merges logs from multiple sources in real-time
- Gracefully handles container restarts and pod rescheduling

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