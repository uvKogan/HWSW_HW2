# HW2 — Olympic Games Management System: Traditional vs FaaS

A single Olympic Games operations system implemented **twice** — so the two
architectures can be compared on performance, resilience, extensibility, and
correctness under concurrency. The thesis is *architecture as a forcing
function*: each side is built the way it is realistically built, and FaaS's
constraints force better structure and rule out whole bug classes.

- **Traditional** (`Traditional/server.py`): a **naive monolith** — the entire
  system in one file, all state in module-level globals (no persistence), every
  operation inlined into one `handle()` dispatcher, on a stdlib `http.server`.
  Fast and simple, but a single point of failure with shared-memory hazards.
- **FaaS** (`FaaS/`): **decoupled** — one small function per file
  (`FaaS/functions/*.py`) over a pure-function core (`common/operations.py`),
  each call a fresh `python3` subprocess with state persisted externally in
  sqlite (`FaaS/storage.py`). Stateless, isolated, independently scalable.

The two are **independent implementations** (not shared code), each validated
by its own unit tests (`common/test_operations.py`, `Traditional/test_monolith.py`).

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

Balanced but FaaS-favored — six axes, measured on an 8-core Linux host:

| Axis | Winner | Why |
|---|---|---|
| Per-call overhead | Traditional | in-memory call vs. fresh interpreter + sqlite round-trip |
| Latency under state growth | Traditional | O(1) in-memory vs. reload-the-whole-blob per call (~O(N²)) |
| Parallel independent CPU (`project_medals`) | **FaaS** | process-per-call multicore (~13.5×) vs. one GIL-bound monolith |
| Fault isolation (`render_highlight` crash) | **FaaS** | one poison call kills the whole monolith + all state; FaaS loses one subprocess |
| Idle footprint | **FaaS** | monolith holds ~20 MB resident 24/7; FaaS scales to zero |
| Cross-request state leak | **FaaS** | monolith's shared `_CTX` mis-attributes bookings; FaaS has no shared context |

Plus ease-of-change (Part 3): a cross-cutting atomic change favors Traditional;
adding an independent operation favors FaaS.

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

`script.sh` runs both sides' unit tests, replays the deterministic workload
through both architectures, and runs all six experiments (and `perf` if
present).

Individual pieces:

```bash
python -m common.test_operations                 # FaaS-core op unit checks
python -m Traditional.test_monolith              # monolith unit checks
python -m common.workload 42 2000 fixture.json   # generate a workload
python -m Traditional.server --workload fixture.json   # Traditional replay
python -m Traditional.server --serve --port 8080       # Traditional as a live HTTP server
python -m FaaS.gateway --workload fixture.json         # FaaS replay
python -m bench.context_leak                           # correctness: cross-request leak (FaaS wins)
python -m bench.fault_isolation                        # resilience: crash blast radius (FaaS wins)
python -m bench.idle_footprint                         # cost: idle memory / scale-to-zero (FaaS wins)
python -m bench.parallel_throughput                    # parallel CPU throughput (FaaS wins)
python -m bench.state_growth                           # latency under state growth (Traditional wins)
python -m bench.seat_race                              # shared-state consistency
```

## Layout

```
common/      FaaS-core business logic (operations.py), reference data, workload, tests
Traditional/ naive monolith (server.py = whole system in one file) + its unit tests
FaaS/        functions (one per op), sqlite storage, gateway, go_live orchestrator
bench/       the six experiments (context_leak, fault_isolation, idle_footprint,
             parallel_throughput, state_growth, seat_race)
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
