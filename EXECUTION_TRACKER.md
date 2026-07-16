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

### Phase A — Reference data (additive, nothing wired yet) — DONE
- [x] A1. Create `common/reference_data.py`: `COUNTRIES` (10 NOCs),
      `ATHLETES` (30, each with country + sport), `VOLUNTEERS` (15),
      `VENUES` (12 real LA28 venues), `USERS` (200 synthetic spectator IDs),
      plus derived O(1) ID lookup sets. Static master data, **not** part of
      mutable `state`.
- [x] A2. Sanity-import + self-check pass on both Windows (`python`) and
      Linux/matanco.space (`python3`). Full placeholder pipeline still
      prints `MATCH` on Linux (setup verified end-to-end).
- [x] **COMMIT**: `3c30bf5` "Add Olympics reference data (...)"

### Phase B — 9 base ops → Olympics domain (Parts 1 & 2 baseline) — DONE
- [x] B1. Rewrote `common/operations.py`: new `initial_state()` (10
      buckets), 9 base ops + validation against `reference_data`, updated
      `OPERATIONS`. (Also pre-added the Part-3 ops `allocate_stream`/
      `recompute_standings`/`go_live` and the benchmark op `project_medals`
      — wired into the workload in later phases.)
- [x] B2. Renamed `FaaS/functions/*.py` stubs to the 9 base ops.
- [x] B3. Rewrote `common/workload.py` (generator + pools from
      `reference_data`); `go_live` held out until Phase C.
- [x] B4. Added `common/test_operations.py` — 8 tests (happy + rejection
      paths). The only real check of op *correctness* (MATCH can't do it).
- [x] B5. `python -m common.test_operations` → 8 pass; pipeline → `MATCH`.
- [x] **COMMIT**: "Rename placeholder ops to Olympic Games domain (9 base ops + sanity tests)"

### Phase C — Part 3 feature: `go_live` cascade (pure Python) — DONE
- [x] C1. `recompute_standings` — deterministic ranked leaderboard from
      `country_scores` into `state["standings"]` (whole-state read).
- [x] C2. `go_live(match_id, venue_id, stream_id)` — cascade:
      `push_live_event` (fan-out) → `allocate_stream` → `recompute_standings`.
      Decomposed into real registered ops so the FaaS orchestrator can chain
      them.
- [x] C3. Naive `FaaS/functions/go_live.py` stub (one fat function, one
      load/save) + `allocate_stream.py` / `recompute_standings.py` stubs.
- [x] C4. Idiomatic `FaaS/orchestrators/go_live_chain.py` — 3
      `gateway.invoke()` calls, no cross-call transaction; documents the
      partial-failure boundary. Verified it yields the correct state.
- [x] C5. `go_live` folded into `common/workload.py`.
- [x] C6. Pipeline → `MATCH` (deterministic standings hold).
- [x] **COMMIT**: "Add Part 3 go_live cascade (fan-out + live standings, pure Python)"

### Phase D — The two concurrency experiments
**D-consistency (Traditional wins): seat-race** — DONE
- [x] D1. `bench/seat_race.py` (+ `bench/_serverctl.py`): N users contend
      for the same seats; double-sells detected from responses (count of
      ok:True per seat), no state-read endpoint needed. Env-gated
      `OLYMPICS_RACE_DELAY` widens the check-then-write window (default off,
      so correctness/perf runs are untouched — MATCH still holds).
- [x] D2. Local result (30 users, 10 seats, 0.02s window): Traditional
      no-lock **3** double-sold, FaaS no-txn **5** double-sold. Both race;
      FaaS harder.
- [x] D3. Traditional fix: `OLYMPICS_TICKET_LOCK` → `threading.Lock` in
      `Traditional/services/__init__.py` dispatch → 0 double-sold.
- [x] D4. FaaS fix: `OLYMPICS_FAAS_TXN` → `transactional_apply` in
      `FaaS/storage.py` holds one connection with `BEGIN IMMEDIATE` across
      load→op→save (`_runtime.py` routes to it) → 0 double-sold. Honest
      caveat in code: it's a *global* state-blob lock, not per-seat.
- [x] D5. Both fixes → 0 double-sold (10 ok / 10 seats, correct).

**D-throughput (FaaS wins): parallel independent CPU** — DONE
- [x] D6. `project_medals` (compute-only, no shared-state writes) +
      compute-only `FaaS/functions/project_medals.py` (bypasses state I/O).
- [x] D7. `bench/parallel_throughput.py`: M concurrent calls at both
      architectures. Local smoke test (8 tasks × 1M iters, 22 cores):
      Traditional 1.07s vs FaaS 0.58s → **FaaS 1.84×**. Clean numbers from
      Linux in Phase F.
- [x] **COMMIT**: "Add concurrency experiments: seat-race (Traditional) + parallel throughput (FaaS)"

### Phase E — Docs — DONE
- [x] E1. `STATUS.json`: scenario set; Part 5 marked skipped.
- [x] E2. `PROJECT.md`: architecture-decisions refreshed (C++ dropped,
      four-axis thesis added), "Open decisions" rewritten, AI-usage-log rows
      added.
- [x] E3. `README.md`: full quickstart (scenario, ops, prereqs, run
      commands, layout).
- [x] Cleanup: removed `common/cpp/`; rewrote `script.sh` (op tests + both
      architectures + correctness gate + both concurrency experiments +
      optional perf; `PYTHON=` override for Windows). Verified end-to-end.
- [→] E4. `report/report.typ` scenario section folded into Phase G (needs
      the Phase F perf numbers anyway).
- [x] **COMMIT**: "Update docs for Olympics scenario"

### Phase F — Part 4 performance (on Linux / matanco.space) — DONE
- [x] F1. `perf stat` over both architectures (base 200-event workload).
      FaaS ≈ 150× Traditional on wall-clock/cycles/instructions; 631×
      context-switches, 123× page-faults. Raw in `results/*/perf_stat.txt`.
- [x] F2. State-growth (`bench/state_growth.py`, N=100..2000): Traditional
      flat (~0.15s); FaaS 8.7→212s, ratio 65×→1258× (≈O(N²) from reloading
      the growing blob per call).
- [x] F3. Parallel throughput on 8 cores: **FaaS 5.86×** (12.4s→2.1s).
      Seat-race on Linux: both race (Trad 4 / FaaS 8 double-sold), both
      fixes → 0.
- [x] F4. All numbers captured in `report/results.md` (feeds the report).
- [x] **COMMIT**: "Add Part 4 performance results (perf, state-growth, both benchmarks)"

### Phase G — Report writing (final pass, ≤6 pages) — DONE (pending IDs)
- [x] G1. Parts 1 & 2 architecture descriptions written.
- [x] G2. Part 3 discussion (naive vs. idiomatic FaaS `go_live`; parts
      changed / risk / extensibility verdict).
- [x] G3. Four-axis comparison with the real Phase F numbers + AI
      disclosure section.
- [x] G4. Compiled `report.typ` → `report.pdf` (4 pages, under the 6 limit)
      and `ids.typ` → `ids.pdf` via typst 0.15 on Linux; pulled to `report/`.
- [ ] ⚠️ `ids.typ` still has placeholder student ID numbers — the team must
      fill the two real IDs (the one thing I can't supply).
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
