# HW2: Olympic Games Management System (Traditional vs FaaS)

> **Live execution tracker** — the approved implementation plan, kept in the
> repo root so progress is visible to both teammates. Checkboxes update as
> work lands. `STATUS.json` / `PROJECT.md` hold coarse per-Part status; this
> file holds the fine-grained steps and commit boundaries.

## Context

HW2 implements the same system twice — a **traditional monolith** (one
long-lived process, shared in-memory state) and a **FaaS** design
(subprocess-per-call, external sqlite state) — then compares them on
performance, extensibility, and security/maintainability. The repo has a
working, verified dual-architecture scaffold whose one piece of real logic
is `common/operations.py`: pure `(state, params) -> result` functions that
**both** architectures call identically. The only differences are how state
is held (in-memory object vs. load/save-per-call) and how calls dispatch
(in-process vs. subprocess-per-call). We are dropping a real domain onto
that scaffold: the **Olympic Games Management System**.

## The comparison thesis (this is what earns the 30% originality)

The two architectures' *defining traits* flip the winner depending on the
workload — that is the whole report:

| Axis | Workload | Winner | Why |
|---|---|---|---|
| **Consistency under concurrency** | seat-race: many buyers contend for the *same* seats | **Traditional** | one in-process `threading.Lock`; FaaS's isolated processes must coordinate through external state (races, or a coarse global blob-lock) |
| **Parallel throughput on independent CPU work** | many heavy, self-contained `project_medals` calls at once | **FaaS** | process-per-call → true multicore; the monolith is a single Python process, GIL-bound to ~1 core for CPU work |
| **Per-call latency + state growth** | the deterministic base-workload replay | **Traditional** | in-memory O(1); FaaS pays process spawn + reloads/reserializes the *entire* (growing) state blob every call |
| **Coupling / atomicity / extensibility** | `go_live` cross-cutting cascade (Part 3) | **Traditional** (easier & safer) | one atomic in-process call vs. orchestrating isolated stateless functions with a real partial-failure gap |

The two concurrency experiments (rows 1 & 2) are the stars: **same theme,
opposite winners.** Rows 3 & 4 are supporting. Honest thesis: *FaaS wins
elastic parallel throughput for independent work; Traditional wins
shared-state consistency, low per-call latency, and atomic cross-cutting
change.*

**No C++.** Pure Python throughout — Python CPU work is exactly what the
GIL serializes, which is what makes the FaaS parallel win vivid. The old
`common/cpp/` accelerator is removed.

## Environment / who runs what

- **This machine is Windows**; interpreter is `python` (not `python3`). Dev
  and correctness runs happen here by invoking modules directly
  (`python -m common.workload ...`, etc.).
- **Profiling (`perf`) and the multicore parallel-throughput numbers run on
  Linux** — the `matanco.space` box (connection set up separately). `perf`
  is Linux-only; the FaaS parallel win needs real cores + cheap `fork`
  (Windows `spawn` would distort it).
- Commits enabled; **staying on `main`**, one commit per phase boundary.
  `git push` remains denied (manual).

## Correctness-gate caveat (drives two design constraints)

`common/compare_states.py` diffs the final Traditional vs. FaaS state
(stripping volatile keys `log`/`updated_at`/`ts`). Because **both
architectures run the identical `common/operations.py`**, this gate can
only catch *architecture-divergence* (JSON round-trip, persistence,
ordering) — it can **never** catch a business-logic bug, since both sides
would compute the same wrong answer. Therefore:
1. **Add a tiny unit-sanity check** on the pure operations (Phase B) — the
   only thing that actually verifies the ops are *correct*.
2. **Keep state JSON-clean**: string dict keys only, lists not tuples, no
   sets — or FaaS's post-serialization state diverges from Traditional's
   and MATCH breaks for a non-logic reason.

## Execution tracker

Each phase ends where the correctness gate still prints `MATCH`; that's the
commit boundary.

### Phase A — Reference data (additive, nothing wired yet)
- [ ] A1. Create `common/reference_data.py`: `COUNTRIES` (~10 NOCs),
      `ATHLETES` (~30, each with country + sport), `VOLUNTEERS` (~15),
      `VENUES` (real LA28 venues: SoFi Stadium, Crypto.com Arena, Rose
      Bowl, BMO Stadium, Dodger Stadium, ...), `USERS` (~200 synthetic
      spectator IDs). Static master data, **not** part of mutable `state`.
- [ ] A2. Sanity-import (`python -c "import common.reference_data"`).
- **COMMIT**: "Add Olympics reference data (countries/athletes/volunteers/venues/users)"

### Phase B — 9 base ops → Olympics domain (Parts 1 & 2 baseline)
- [ ] B1. Rewrite `common/operations.py`: new `initial_state()` (buckets:
      `venues`, `matches`, `volunteers`, `shuttles`, `restaurant_bookings`,
      `subscriptions`, `country_scores`, `standings`, `streams`, `log`),
      the 9 base ops (see catalog below), updated `OPERATIONS` registry.
      Entity params validated against `reference_data` (unknown ID →
      `{"ok": False, ...}`). Keep `_log`/`_now`; keep state JSON-clean.
- [ ] B2. Rename/rewrite `FaaS/functions/*.py` stubs to match (one 4-line
      `_runtime.run("...")` file per op).
- [ ] B3. Rewrite `common/workload.py`'s if/elif generator + pool
      constants to the 9 ops, drawing IDs from `reference_data` pools.
- [ ] B4. Add a small `common/test_operations.py` (or inline asserts):
      exercise each op's happy path + one rejection path (seat already
      sold, unknown country, capacity ceiling). Pure functions → trivial.
- [ ] B5. Run the pipeline (`python -m common.workload ...`, both
      architectures, `python -m common.compare_states ...`); confirm
      `MATCH`.
- **COMMIT**: "Rename placeholder ops to Olympic Games domain (9 base ops + sanity tests)"

### Phase C — Part 3 feature: `go_live` cascade (pure Python)
- [ ] C1. Add `recompute_standings(state, params)` to
      `common/operations.py`: deterministic aggregation over
      `country_scores` (+ athletes) → ranked leaderboard into
      `state["standings"]`. Whole-state read → naturally exposes FaaS's
      reload cost. Register in `OPERATIONS`.
- [ ] C2. Add `go_live(state, params={match_id, venue_id, stream_id})`:
      calls `push_live_event` (fan-out to subscribers) → allocates
      `state["streams"][stream_id]` → calls `recompute_standings`. One
      cross-cutting business transaction. Register in `OPERATIONS`.
- [ ] C3. Add naive `FaaS/functions/go_live.py` stub (the "architectural
      cheat": one fat function bundling 3 ops behind one load/save).
- [ ] C4. Add idiomatic `FaaS/orchestrators/go_live_chain.py` — NOT in
      `OPERATIONS`; calls `FaaS.gateway.invoke()` three times in sequence
      (3 spawns, 3 load/save round trips, **no cross-call transaction** →
      crash after step 2 leaves match live/streaming but standings stale;
      a state Traditional's single call cannot reach). This diff *is* the
      Part-3 payload.
- [ ] C5. Fold `go_live` into `common/workload.py`'s generator (pure
      Python now → no native build dep, safe in the main workload).
- [ ] C6. Re-run the pipeline; confirm still `MATCH` (deterministic
      standings ⇒ diff holds).
- **COMMIT**: "Add Part 3 go_live cascade (fan-out + live standings, pure Python)"

### Phase D — The two concurrency experiments
**D-consistency (Traditional wins): seat-race**
- [ ] D1. `bench/seat_race.py`: seed one match with a small seat pool
      (`seat0..seat9`); draw N≈30 users deliberately targeting the *same*
      seats. Fire N concurrent `book_ticket` calls via `ThreadPoolExecutor`
      — against Traditional `--serve` (`/invoke` POSTs) and against
      `FaaS.gateway.invoke()` (subprocess each). Read back
      `matches[m]["seats"]`; report any seat sold to >1 user (last-writer
      clobber) or lost.
- [ ] D2. Run with no fix; capture ≥1 reproduced double-sold/lost seat on
      the FaaS side.
- [ ] D3. Traditional fix: a `threading.Lock` around `book_ticket`'s
      critical section in `Traditional/services/__init__.py`'s dispatch.
- [ ] D4. FaaS fix: this requires more than a one-liner — `_runtime.py`'s
      `load_state()`/`save_state()` are **separate connections**, so a
      transaction must span load→op→save. Add a `book_ticket`-path that
      holds one sqlite connection with `BEGIN IMMEDIATE` across the whole
      cycle (or a compare-and-swap in `save_state`). Note honestly in the
      report: because state is one JSON blob in one row, this is a *global*
      state lock, not per-seat — the coarse-external-state tax.
- [ ] D5. Re-run; confirm zero double-sold seats both sides.

**D-throughput (FaaS wins): parallel independent CPU**
- [ ] D6. Add `project_medals(state, params={country_code, iterations})`
      to `common/operations.py`: CPU-heavy Monte Carlo medal projection,
      reads only params + `reference_data`, **returns** a result, writes
      **no** shared state (so concurrent calls don't contend — the clean
      embarrassingly-parallel case). Register in `OPERATIONS`. Its FaaS
      function is compute-only (bypasses load/save state I/O) so the
      benchmark measures compute, not blob serialization.
- [ ] D7. `bench/parallel_throughput.py`: fire M concurrent `project_medals`
      calls (M ≈ cores × k) at both architectures via `ThreadPoolExecutor`;
      measure wall-clock + speedup. Tune `iterations` so per-call compute
      ≫ spawn cost. (Real numbers come from the Linux run in Phase F.)
- **COMMIT**: "Add concurrency experiments: seat-race (Traditional) + parallel throughput (FaaS)"

### Phase E — Docs
- [x] E1. `STATUS.json`: scenario set to "Olympic Games Management
      System"; Part 5 marked skipped. *(done)*
- [ ] E2. `PROJECT.md`: refresh architecture-decisions (drop C++, add the
      four-axis thesis), rewrite "Open decisions / TODO", add AI-usage-log
      rows for the planning rounds.
- [ ] E3. `README.md`: quickstart — scenario, prereqs (stdlib Python;
      Linux for perf), how to run the pipeline + the two benchmarks,
      directory map, pointer to `PROJECT.md`.
- [ ] E4. `report/report.typ`: fill "System Scenario" (9 base ops +
      reference-data layer; `go_live`, `project_medals` called out).
- **COMMIT**: "Update docs for Olympics scenario"

### Phase F — Part 4 performance (on Linux / matanco.space)
- [ ] F1. `perf stat`/`perf record` over both architectures on the base
      workload (`profiling/run_perf_*.sh`); capture execution time, CPU
      cycles, context switches, memory, syscalls.
- [ ] F2. **State-growth scaling**: run the base workload at N =
      100/500/1000/2000/5000 events; tabulate total + per-call time. Expect
      FaaS to climb (reload-the-world per call), Traditional ~flat.
- [ ] F3. Run both benchmarks on multicore Linux: seat-race
      (consistency/correctness, before+after fix) and parallel-throughput
      (FaaS speedup vs. cores). Record the numbers.
- [ ] F4. Fill `report/report.typ` Part 4 tables + narrative explaining
      *why* each result makes sense.
- **COMMIT**: "Add Part 4 performance results to report"

### Phase G — Report writing (final pass, ≤6 pages)
- [ ] G1. Parts 1 & 2 architecture descriptions.
- [ ] G2. Part 3 discussion (naive vs. idiomatic FaaS `go_live`; how many
      parts change, how risky, which extends easier).
- [ ] G3. The four-axis comparison as the analytical core; AI Tool Usage
      Disclosure section.
- [ ] G4. Fill `ids.typ` with real student IDs; compile both `.typ` → PDF
      (Linux/`typst` if available).
- **COMMIT**: "Write HW2 report content"

## Operation catalog

### Base ops (in the deterministic correctness workload)

| # | Operation | Params | State bucket | Behavior |
|---|---|---|---|---|
| 1 | `book_venue_slot` | `venue_id`, `match_id` | `venues` (`status`, `held_by`) | Reserve a venue for a session; deny if occupied. |
| 2 | `release_venue_slot` | `venue_id` | `venues` | Free a venue. |
| 3 | `book_ticket` | `match_id`, `seat_id`, `user_id` | `matches` (`seats: {seat_id→user_id}`) | Reserve one specific seat; deny if already sold. `user_id` ∈ `USERS`. **Reused by the seat-race demo.** |
| 4 | `assign_volunteer` | `volunteer_id`, `venue` | `volunteers` | Assign a volunteer (∈ `VOLUNTEERS`) to a venue. |
| 5 | `dispatch_shuttle` | `shuttle_id`, `route`, `seats` | `shuttles` | Assign a shuttle to a route; track passengers vs. a seat ceiling. |
| 6 | `reserve_restaurant_table` | `athlete_id`, `restaurant_id`, `party_size` | `restaurant_bookings` | Reserve a dining slot for an athlete (∈ `ATHLETES`). |
| 7 | `subscribe_to_updates` | `subscriber_id`, `topic` | `subscriptions` (`topic→[ids]`) | Register interest in a match/country's live updates. |
| 8 | `push_live_event` | `match_id`, `event_type`, `details` | `matches[…]["status"]`, `log` | Fan out one delivery record per subscriber + one match event (pub/sub). |
| 9 | `update_country_score` | `country_code`, `medal` | `country_scores` | Adjust a country's medal tally (∈ `COUNTRIES`). |

### Part 3 feature
- `recompute_standings(state, params)` — deterministic whole-state
  aggregation → `state["standings"]` (helper + standalone op).
- `go_live(state, params)` — cross-cutting cascade: `push_live_event` →
  allocate `streams[stream_id]` → `recompute_standings`.

### Perf-demo op (NOT in the correctness workload)
- `project_medals(state, params={country_code, iterations})` — CPU-heavy,
  independent, read-only Monte Carlo projection; **returns** result, writes
  no shared state. The FaaS-parallel-win vehicle. FaaS entry is
  compute-only (no state load/save).

## File-by-file summary

- **New**: `common/reference_data.py`, `bench/seat_race.py`,
  `bench/parallel_throughput.py`, `common/test_operations.py`,
  `FaaS/orchestrators/go_live_chain.py`, plus new `FaaS/functions/` stubs
  for the renamed ops + `go_live.py` + a compute-only `project_medals.py`.
- **Rewrite**: `common/operations.py` (9 ops + `recompute_standings` +
  `go_live` + `project_medals` + new `initial_state`), `common/workload.py`
  (generator + pools), `README.md`, `report/report.typ` scenario section,
  `PROJECT.md` (architecture + open-decisions + AI log).
- **Small edits**: `Traditional/services/__init__.py` (seat lock),
  `FaaS/functions/_runtime.py` + `FaaS/storage.py` (transaction spanning
  load→op→save for the seat fix).
- **Remove**: `common/cpp/` (accelerator + build.sh); drop the accelerator
  bullet from docs. `profiling/make_flamegraph.sh` + `flamegraph/` may stay
  as unused optional tooling.
- **Unchanged**: `Traditional/server.py`, `FaaS/gateway.py`,
  `common/compare_states.py`, `script.sh` (aside from `python3`→portable
  interpreter handling if we later run it on Linux, which is fine there).

## Verification

- Base pipeline prints `MATCH` (Traditional vs. FaaS final state).
- `common/test_operations.py` passes (op correctness — the thing MATCH
  can't check).
- `bench/seat_race.py`: reproduces ≥1 double-sold seat pre-fix, zero
  post-fix, on both architectures.
- `bench/parallel_throughput.py` on multicore Linux: FaaS wall-clock beats
  Traditional for the CPU-bound independent batch; Traditional flat/serial.
- Manual spot checks: `book_ticket` twice on one seat denies the second;
  `subscribe_to_updates` then `push_live_event` yields a delivery record
  per subscriber; `go_live` produces a standings update.
