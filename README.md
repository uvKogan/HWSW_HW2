# HW2 — Olympic Games Management System: Traditional vs FaaS

A single Olympic Games operations system implemented **twice** — as a
traditional monolith and as a Function-as-a-Service design — so the two
architectures can be compared on performance, extensibility, and concurrency
behaviour. Both implementations call the *same* business logic
(`common/operations.py`); only the execution model differs.

- **Traditional** (`Traditional/`): one long-lived process, all state in
  memory, a stdlib `http.server` (no framework). Dispatch is a direct
  in-process function call.
- **FaaS** (`FaaS/`): each operation call is a fresh `python3` subprocess
  (`FaaS/functions/*.py`), with state persisted externally in sqlite
  (`FaaS/storage.py`). Stateless, isolated, minimal inter-function coupling.

## The 9 operations (Parts 1 & 2)

`book_venue_slot`, `release_venue_slot`, `book_ticket` (seat-level),
`assign_volunteer`, `dispatch_shuttle`, `reserve_restaurant_table`,
`subscribe_to_updates`, `push_live_event` (pub/sub fan-out),
`update_country_score`. Entity IDs are validated against a fixed roster in
`common/reference_data.py` (countries, athletes, volunteers, real LA28
venues, spectator users).

## Part 3 feature — `go_live` cascade

A cross-cutting transaction fired when a match goes live: announce to
subscribers → put a broadcast stream on air → recompute the medal standings.
Traditional runs it as one atomic in-process call; FaaS has a naive
single-function port and an idiomatic three-call orchestrator
(`FaaS/orchestrators/go_live_chain.py`) that exposes a partial-failure gap.

## The comparison (Part 4)

The two architectures' defining traits flip the winner by workload:

| Workload | Winner | Why |
|---|---|---|
| Contended shared state (seat-race) | Traditional | one in-process lock vs. coordinating through external state |
| Independent parallel CPU (`project_medals`) | FaaS | process-per-call multicore vs. one GIL-bound monolith |
| Per-call latency + state growth | Traditional | in-memory vs. reload-the-whole-blob per call |
| Atomic cross-cutting change (`go_live`) | Traditional | one atomic call vs. chaining isolated functions |

## Prerequisites

- **Python 3** (standard library only — no third-party packages).
- **Linux** for Part 4 profiling (`perf`) and the clean multicore
  parallel-throughput numbers. The correctness runs and both benchmarks work
  anywhere Python 3 does.
- `typst` (optional) to compile the report under `report/`.

## Run it

```bash
./script.sh                 # Linux/macOS (python3)
PYTHON=python ./script.sh   # Windows (Git Bash), where the launcher is `python`
```

`script.sh` runs the op sanity tests, replays the deterministic workload
through both architectures, checks their final states match, and runs both
concurrency experiments (and `perf` if present).

Individual pieces:

```bash
python -m common.test_operations                 # op-correctness unit checks
python -m common.workload 42 200 fixture.json    # generate a workload
python -m Traditional.server --workload fixture.json   # Traditional replay
python -m Traditional.server --serve --port 8080       # Traditional as a live HTTP server
python -m FaaS.gateway --workload fixture.json         # FaaS replay
python -m bench.seat_race                              # concurrency: seat-booking race
python -m bench.parallel_throughput                   # concurrency: parallel CPU throughput
```

## Layout

```
common/      shared business logic (operations.py), reference data, workload, tests
Traditional/ monolith: in-memory state + stdlib HTTP server
FaaS/        functions (one per op), sqlite storage, gateway, go_live orchestrator
bench/       the two concurrency experiments
profiling/   perf wrappers for Part 4
report/      Typst report + team IDs
```

## Submission

```bash
./make_submission.sh   # rebuilds report.pdf + ids.pdf and assembles HW2.zip
```

Real student IDs are **not** in the repo: put them in the gitignored
`report/ids.local` (`MATAN_ID=…`, `YUVAL_ID=…`) and they're injected into
`ids.pdf` at compile time. Needs `typst` (`TYPST=~/bin/typst ./make_submission.sh`
to point at a local binary) and `zip`. Measured Part 4 numbers are in
`report/results.md`.

See `PROJECT.md` for full status and design decisions, `EXECUTION_TRACKER.md`
for the phase-by-phase build log, and `prompts.md` for the AI-usage record.
