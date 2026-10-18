# loglens

**Tail `docker compose`, Kubernetes pods, log files and arbitrary commands as one time-ordered, colour-coded stream, for people debugging more than one service at once.**

An incident rarely lives in one container. You end up with four terminals, `kubectl logs -f` in one, `docker compose logs` in another, and you squint at timestamps to work out whether the 502 came before or after the payment timeout. loglens reads all of them, sorts by the timestamp each line actually carries, and prints one stream with a coloured service column.

Three sample logs ship in `examples/`, so you can try it without Docker:

```console
$ loglens --no-follow --file examples/api.log --file examples/payments.log --file examples/db.log
db       | 09:15:00.000 db ready
payments | 09:15:01.950 INFO payments worker ready
api      | 09:15:02.104 INFO listening on :8080
api      | 09:15:03.870 INFO GET /orders/42 200 12ms
db       | 09:15:03.900 {"time":"2024-05-14T09:15:03.900Z","level":"info","msg":"checkpoint complete"}
payments | 09:15:03.980 INFO charge order=42 amount=1999 USD
api      | 09:15:04.215 WARN slow upstream: payments took 1480ms
db       | 09:15:04.500 WARN connection pool 18/20 in use
payments | 09:15:04.760 ERROR stripe: read timeout after 3000ms, closing socket
api      | 09:15:04.912 ERROR POST /orders 502 upstream payments: connection reset
api      | 09:15:04.912 Traceback (most recent call last):
api      | 09:15:04.912   File "api/handlers.py", line 88, in create_order
api      | 09:15:04.912     charge = payments.charge(order)
api      | 09:15:04.912 ConnectionResetError: [Errno 104] Connection reset by peer
payments | 09:15:05.100 WARN retry queue depth=7
api      | 09:15:06.003 INFO GET /health 200 1ms
```

The `payments` timeout at 04.760 sits right before the `api` 502 at 04.912, which is the whole story. The stack trace has no timestamp of its own, so it stays glued to the error line it belongs to. In a terminal each service gets its own colour and error lines are red.

Cut it down to what matters:

```console
$ loglens --no-follow --file examples/api.log --file examples/payments.log --file examples/db.log --level error --exclude db
payments | 09:15:04.760 ERROR stripe: read timeout after 3000ms, closing socket
api      | 09:15:04.912 ERROR POST /orders 502 upstream payments: connection reset
api      | 09:15:04.912 Traceback (most recent call last):
api      | 09:15:04.912   File "api/handlers.py", line 88, in create_order
api      | 09:15:04.912     charge = payments.charge(order)
api      | 09:15:04.912 ConnectionResetError: [Errno 104] Connection reset by peer
```

## Install

loglens is not on PyPI. From a clone:

```bash
pip install -e .
```

It has no runtime dependencies and needs Python 3.11 or newer. The `docker` and `kubectl` sources need those tools on your `PATH`; files, stdin and `--cmd` do not.

## Usage

```bash
loglens                                           # docker compose logs, whole project in the current directory
loglens --services web --services db --limit 200  # only those compose services, stop after 200 lines
loglens --k8s api-7d9 --k8s worker-5f2 -n prod    # specific pods
loglens -l app=api -n prod --reconnect            # every pod matching a label, re-attach on restarts
loglens --file api=/var/log/api.log --file -      # files (NAME= labels them) and standard input
loglens --cmd 'edge=ssh edge1 journalctl -f -o short-iso'   # any command that prints log lines
loglens --level warn --grep timeout -i            # severity and regex filters
loglens --filter 'api*' --exclude api-canary      # service filters, globs allowed
loglens --since 10m --tail 100 --no-follow        # recent history, then exit
loglens --json                                    # one JSON object per line, for jq
```

Sources can be mixed freely, for example `--compose --k8s api-7d9 --file edge=edge.log`. Run `loglens --help` for every flag. Exit status is 0 on success, 2 for a usage error or an unusable source (missing `docker`, unreadable file, `kubectl` failing), and 130 when interrupted.

## How it works

- **Sources** run `docker compose logs --timestamps`, `kubectl logs --timestamps`, or read a file, stdin or any command, one thread each. Every line becomes an entry of timestamp, service and message. The service comes from the compose container prefix (with the `-1` replica suffix removed), the pod name, or the name you gave.
- **Timestamps** are parsed from the front of each line (RFC 3339 with nanoseconds, numeric offsets, `UTC` suffixes, epoch values) or from a JSON `time` / `ts` / `timestamp` field. Lines without one, such as stack trace frames, inherit the previous line's timestamp for that service.
- **Merging** uses a heap. A line is released once every active source has produced something at least as new, or once it has waited `--window` seconds (default 0.5). Finite inputs therefore come out perfectly ordered, and a quiet live source can delay output by at most the window.
- **Filtering** by service (exact or glob), regex and severity. Severity is read from a JSON `level` field, `level=` pairs, or a word like `ERROR` near the start of the line; lines with no recognisable level share the one before them.
- **Colour** is picked from a CRC of the service name, so `api` is the same colour every run. Output is plain when it is not a terminal, honouring `NO_COLOR`.
- **Reconnect** (`--reconnect`) re-runs an ended `docker`, `kubectl` or `--cmd` stream and resumes from the last timestamp seen, dropping lines it already printed.

## Limitations

- The Docker Compose and Kubernetes sources have only been exercised against stand-in `docker` and `kubectl` executables that print real-format output; this machine has neither tool, so they have not been run against a live daemon or cluster.
- Live ordering is best effort. A line that arrives more than `--window` seconds after a newer one from another service is printed out of order. Clock skew between hosts is not corrected.
- Timestamps without a zone are treated as UTC. A line with no timestamp at all, before any timestamped line from its service, gets the time it was received.
- Replica suffixes are guessed: a compose container named `redis-6` is shown as `redis`. Compose lines that lack the `name | ` prefix (the `Attaching to` banner, warnings) are dropped.
- Severity detection is a heuristic, and `--level` keeps lines it cannot classify.
- With a label selector, `kubectl` itself caps concurrent streams (five by default).
- Nothing is stored, and the internal queue is unbounded if your terminal is slower than the logs.
- Colour on Windows needs a terminal with ANSI support (Windows Terminal, recent conhost).

## Development

```bash
pip install -e ".[dev]"
pytest -q
ruff check .
```

The tests run real subprocesses and put fake `docker` / `kubectl` executables on `PATH`, so they need no Docker. CI runs Linux and Windows on Python 3.11 and 3.13.

## Licence

MIT, see [LICENSE](LICENSE).
