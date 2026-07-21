# Mixed-Burst Throughput Test — Full Task Summary

> **Purpose**: raw context for the report-writing agent. Chronological log of
> how `bench/mixed_burst.py` (+ its two helper modules) came to exist, what it
> found, and — importantly — a genuine mid-stream discovery that changed the
> headline result. Nothing here is polished for the report; it's the full
> trail (idea → code → tests → surprise) so the report can cite the real
> reasoning instead of a cleaned-up-after-the-fact narrative.

## 1. The idea (where this started)

Existing `bench/*.py` scripts (`seat_race.py`, `context_leak.py`,
`fault_isolation.py`, `idle_footprint.py`, `parallel_throughput.py`,
`state_growth.py`) each isolate exactly **one** variable — one op, one bug
class, fired all-at-once via `ThreadPoolExecutor(max_workers=len(tasks))`.
That's good for proving individual point-claims but doesn't look anything
like how the Games would actually be hit in practice.

The user's original vision (verbatim intent): a database of thousands of
timestamped entries — a venue booked, an athlete ordering food for their
teammates, another team hammering a nearly-full hotel, a popular match's
stream peaking, a ticket-buying stampede on that match, athletes shuttling
back afterward — all existing operations, randomized, "multiplied by
hundreds," as a workload realistic enough to show FaaS actually winning
somewhere in the real world, not just in a synthetic single-variable test.

Two clarifying questions came up before any design work:

1. **"We only simulate 200 users — what if we go to 2k or 20k?"** Correction:
   `N_USERS=200` in `common/workload.py` is just an ID pool size for the
   *sequential* correctness/perf replay, not a concurrency setting. The real
   concurrency test (`bench/seat_race.py`) defaults to 30 concurrent users.
   Scaling that number up would NOT straightforwardly favor FaaS: (a)
   correctness is already binary at 30 users — more buyers just makes the
   *unguarded* bug's double-sell count uglier, it doesn't change whether the
   fix works; (b) `FaaS.gateway.invoke` spawns a real OS subprocess per call
   via `subprocess.run`, and the existing benches fire every task at once —
   at 20,000 simultaneous users that's 20,000 simultaneous interpreter
   spawns, a fork-storm that would exhaust the OS, not a realistic serverless
   burst (a real platform queues/autoscales gradually).
2. **"Isn't there already a mixed, realistic, over-time simulation?"** No —
   `common/workload.py` generates a realistic *mixture* of all ops with
   collisions built in, but replays it strictly **sequentially**, one event
   at a time, purely for state-equivalence checking and `perf` profiling.
   Every `bench/*.py` script deliberately isolates one op/one variable. There
   was no benchmark firing a mixed, concurrent, bursty, multi-op load from
   simulated users over time — that was a real, legitimate gap.

## 2. Constraints set before design started

- **Do not modify any existing file** — additive only (new files under
  `bench/`).
- **Plan the burst around this machine's actual hardware** — 8 logical cores
  (Intel Core Ultra 7 258V), 15GB RAM, Linux/WSL2 (checked via `nproc`/`free`
  directly).
- **Keep the test short** to run, while still exposing that FaaS wins under
  stressed load.
- **Show live progress** (percentage + ETA) while a run is in flight, since
  full runs take real wall-clock time.
- Work in discrete, self-verified steps — run something and inspect the
  output after each step, not one big write-then-test at the end.

## 3. Investigation before writing any code

Used an Explore agent + direct file reads to establish ground truth before
designing anything (avoids guessing about mechanisms that turned out to
matter a lot later):

- **`FaaS/storage.py`**: state is a single JSON blob in one sqlite row. Two
  access paths: naive `load_state()`/`save_state()` (separate connections —
  a lost-update race) and `transactional_apply()` (one connection, `BEGIN
  IMMEDIATE` + `PRAGMA busy_timeout=10000`), toggled globally by
  `OLYMPICS_FAAS_TXN`. **This is a global lock on the whole state blob, not
  per-entity locking.**
- **`Traditional/server.py`**: module-level global dicts; `threading.Lock`
  gated by `OLYMPICS_TICKET_LOCK`, wrapping **every** op's entire dispatch
  when enabled (not scoped to ticketing) — also global, not fine-grained.
  `ThreadingHTTPServer`, so concurrent requests are Python threads sharing
  one process and one GIL.
- **Key implication**: because both architectures' "safe" mode is a *global*
  lock/txn, a contended-op burst with locks on does **not** show FaaS winning
  on serialization — both fully serialize. The one **honest, demonstrable**
  FaaS-wins-under-load axis available in this codebase is genuine CPU-bound,
  independent work (`project_medals`, no shared state at all) — the same
  axis `bench/parallel_throughput.py` already proves in isolation.
- **No charting convention exists anywhere in the repo** (`grep -r
  matplotlib\|pyplot` returned nothing) — `report/results.md` is all markdown
  tables; the only figures are `perf`-generated flamegraphs.
- Confirmed reusable plumbing: `bench/_serverctl.py` (start/stop/post_invoke
  for Traditional over HTTP), `FaaS.gateway.invoke` (subprocess-per-call),
  `FaaS.storage.reset_state`/`load_state`, `common.reference_data` (12
  venues, 15 volunteers, 30 athletes, 10 countries, 200 users),
  `common/workload.py`'s bounded-pool param-generation pattern.

## 4. Design decisions confirmed with the user before coding

Asked explicitly (via structured question, not assumed) and got answers on
four forks:

1. **No "hotel" op exists** — stand-in agreed: a `dispatch_shuttle` capacity
   race (pre-fill one shuttle near capacity, then a concurrent boarding
   spike on it). A genuine, previously-untested check-then-increment race,
   same bug class as the seat race.
2. **Output format** — no charting library exists in the repo today; user
   chose to **add a matplotlib chart** anyway (on top of a markdown table),
   accepted as a new, isolated, lazily-imported soft dependency scoped to one
   flag in one file.
3. **Lock/txn toggle** — kept as an **optional flag** (`--lock`/`--txn`), not
   a default reported axis, so the default report stays focused on the
   throughput story rather than re-litigating the global-lock nuance every
   run.
4. **`go_live`** — use the bundled op (not the 3-call `go_live_chain`
   orchestrator), keeping timeline/timestamp accounting simple (1 event = 1
   invocation, like every other op).

## 5. What got built

Three new files, nothing existing touched:

- **`bench/burst_workload.py`** — timestamped, narrative-shaped event
  generator. Seven phases on one compressed "Games day": `background_trickle`
  (spans the whole run), `hotel_shuttle_prefill`, `streaming_peak`,
  `hotel_shuttle_spike`, `ticket_rush_spike`, `live_medal_projection`,
  `wind_down`. Every op in `common.operations.OPERATIONS` is exercised at
  least once (including a standalone `allocate_stream` call, which otherwise
  only ever runs as a side-effect inside `go_live`'s cascade — caught by the
  generator's own self-check). Contended events are pinned to shared targets
  (`POPULAR_MATCH`, a small `POPULAR_SEATS` pool, `HOTEL_SHUTTLE_ID`) so
  collisions are scripted, not left to chance. `--summary` CLI mode
  self-checks event counts, phase time windows, and pinning.
- **`bench/bounded_dispatch.py`** — the actual new piece of infrastructure.
  Every existing bench script fires its whole task list at once
  (`max_workers=len(tasks)`); this instead **paces submission** to each
  event's scheduled timestamp and **caps concurrent execution** with a fixed
  thread pool, so a burst applies real bounded pressure instead of either a
  fork-storm or full serialization. Includes the requested **live progress
  reporting**: an in-place (`\r`) stderr line — `X% (n/total, phase: <name>)
  — elapsed Ns, ETA ~Ms` — with ETA recomputed from each phase's own
  observed completion rate (a single whole-run rate estimate would be
  misleading, since the CPU-bound medal phase has a very different per-event
  cost than the I/O/lock-bound phases). `--selftest` mode verifies, against a
  synthetic stub: the concurrency cap actually holds, a scripted spike drains
  over the expected time window (not instantly), and steady events track
  their requested schedule with ~0 drift.
- **`bench/mixed_burst.py`** — orchestrates both architectures through the
  dispatcher, then reports two **separate, non-conflated** results:
  correctness (seat/shuttle lost-updates, reusing `seat_race.py`'s
  tally-by-response-count pattern) and phase-scoped latency/throughput
  (`(last end − first start)` wall-clock and `count/wall` throughput per
  phase — not a whole-run average, since that would blur the CPU-bound
  phase's very different behavior into the rest).
- **`bench/burst_chart.py`** — optional matplotlib figure (phase-scoped wall
  time + throughput, both architectures, the CPU-bound phase highlighted),
  lazily imported only when `--chart-out` is passed so the rest of the
  benchmark stays runnable without the dependency.

Full CLI on `mixed_burst.py`: `--seed`, `--scale`, `--pool-size`,
`--iterations` (medal), `--arch {traditional,faas,both}`, `--lock`, `--txn`,
`--race-delay`, `--json-out`, `--chart-out`. `script.sh` was deliberately
**not** modified — this stays a standalone `python -m bench.mixed_burst`
command, per the additive-only constraint.

## 6. Step-by-step build with self-checks (what was actually verified, not just written)

1. **Generator standalone** (`--summary`): 562 events at scale 1.0 (original
   defaults), all 14 ops present, every phase's events fell inside its
   intended time window, pinned IDs (popular match/seats, hotel shuttle)
   verified shared across their phases.
2. **Dispatcher against a stub** (`--selftest --pool-size 8`): max observed
   concurrency held at ≤8, a scripted 20-event spike drained in ~0.15s
   (matches the expected `ceil(20/8)×0.05s` model), steady events showed
   ~0.000s schedule drift. Exit code 0.
3. **FaaS-only, reduced scale**: no exceptions across all 14 op types;
   `FaaS.storage.load_state()` confirmed populated across every state bucket
   (venues, matches, shuttles, restaurant_bookings, subscriptions,
   country_scores, streams).
4. **Traditional path added**: clean server start/stop (`ps aux` confirmed no
   leaked process afterward — an initial `pgrep -f` check gave a false
   positive that direct `ps aux` resolved), `get_state` returned a populated
   snapshot pre-shutdown.
5. **Correctness tallies + phase stats, both archs, reduced scale**: races
   showed up with locks/txn off; the medal-projection phase already trended
   FaaS-favorable even at 10% scale.
6. **Calibration at full scale** — this is where the first bug and the first
   tuning pass happened (below).
7. **Chart output**: rendered and visually inspected — readable axis labels,
   legend, both architectures color-distinguished, the CPU-bound phase
   highlighted in gold.
8. **Final CLI pass**: clean full-default run, exit code 0; separately
   verified `--lock --txn` together drive both architectures' double-sell and
   lost-update counts to zero (confirms the global-lock finding from step 3's
   investigation is correct in practice, not just in the source).

## 7. A real bug caught by the self-checks (not cosmetic)

At `--scale 0.1` for smoke testing, event **counts** shrank as intended, but
phase **time windows** did not — so the same number of seconds got fewer
events spread across it, diluting burst density. Symptom: the
`live_medal_projection` phase showed Traditional and FaaS at near-identical
wall-clock time at reduced scale, because with only ~6 medal calls spread
over a full untouched 1-second window, they were arriving one every ~167ms —
never actually overlapping, so there was no concurrency for FaaS to exploit
in the first place. Fixed by scaling each phase's time window by the same
factor as its event count, so burst *density* (events/second within a phase)
stays constant regardless of `--scale` — a reduced-scale smoke test now
compresses the whole run rather than thinning out a fixed-duration window.

## 8. Calibration pass (first tuning cycle)

First full-scale run (original defaults: 64 medal calls × 300,000 iterations
each) gave only a **1.8x** FaaS speedup on the medal phase — too thin to call
"clear." Root cause: at 300k iterations, `project_medals`'s own compute time
per call is small enough that the ~44ms fixed subprocess-spawn overhead (per
`bench/idle_footprint.py`'s own measurement) ate a large fraction of FaaS's
per-call time, diluting the parallelism win. Raised `MEDAL_ITERATIONS` to
1,000,000 (so compute dominates over fixed spawn overhead) and re-ran full
scale **three times** to check for noise, not just one lucky run:

| run | live_medal_projection speedup |
|---|---|
| 1 | 2.91x |
| 2 | 2.70x |
| 3 | 2.93x |

Stable in the 2.7-2.93x band. Correctness numbers were also stable across the
three runs: Traditional double-sold 3/20 seats every time (deterministic
seed + fixed `OLYMPICS_RACE_DELAY` widening the window), FaaS double-sold
19-20/20 every time (naive load/save collides almost every time at this
buyer/seat contention ratio), and the shuttle-capacity lost-update
reproduced on the FaaS side each run (noted in the report output itself as
*opportunistic*, since — unlike `book_ticket` — `dispatch_shuttle` has no
artificial race-window hook in `common/operations.py`, and that file was not
modified to add one; the FaaS naive path's larger real per-call latency,
from actual subprocess+sqlite I/O, is simply what makes it the side more
likely to expose the race).

Total wall time for both architectures together: ~16-17 seconds. Comfortably
inside the "keep it short" constraint.

## 9. Change in perspective: "enlarge the workload to give FaaS better results"

After seeing the 2.7-2.93x result, the user asked to enlarge the workload —
push toward hundreds/thousands of requests — specifically **to make FaaS's
win more pronounced** under a "fully loaded monolith."

This required pushing back on the framing before touching any code, because
naively scaling *everything* up would not do what was asked, and could
actively undermine the honest story already built:

- For the **state-touching ops** (tickets, shuttles, background traffic),
  each call is cheap in-memory work. FaaS pays a fixed subprocess-spawn +
  sqlite round-trip tax on top with no compensating parallelism benefit for
  small sequential state mutations. Scaling *that* axis up would only widen
  Traditional's raw-throughput lead — the same conclusion already reached
  when discussing scaling `seat_race.py` to thousands of users, earlier in
  this task.
- The **one** axis where more load genuinely helps FaaS is the CPU-bound
  `live_medal_projection` phase: real, independent, parallelizable work,
  where more of it (or heavier per-call compute) directly grows FaaS's
  structural core-count advantage.

Recommendation given and acted on: grow the medal-projection phase
specifically (both call count and per-call compute), and separately bump
overall `--scale`/event volume for narrative realism ("hundreds/thousands of
entries") — while being explicit that the non-CPU phases would show
Traditional's lead *widen*, not narrow, at higher volume, and that this is
the correct, honest result rather than a flaw to fix.

## 10. Changes made in response

In `bench/burst_workload.py`:
- `live_medal_projection` phase count: **64 → 150** calls (base count in
  `_PHASE_SPEC`).
- Default `medal_iterations`: **1,000,000 → 2,000,000** (both in
  `generate_timeline()`'s signature and the module's own `--iterations` CLI
  default).
- `TOTAL_EVENTS_AT_SCALE_1`: 562 → 648 (auto-computed via `sum()`; the
  inline comment was updated to match).

In `bench/mixed_burst.py`:
- `--iterations` CLI default: 1,000,000 → 2,000,000, to match.

Verified the generator's own self-check still passed after the edit (648
total events, medal-phase count = 150, no missing ops) before running the
full benchmark.

## 11. The surprising result (the headline finding)

Running the enlarged workload produced a much bigger effect than just a
better CPU-phase ratio — and a **different kind** of result than what was
being tuned for:

| phase | before (64×1M) | after (150×2M) |
|---|---|---|
| `live_medal_projection` — Traditional | ~4.7-4.9s | **22.1-22.8s** |
| `live_medal_projection` — FaaS | ~1.6-1.7s | **5.8-6.2s** |
| `live_medal_projection` speedup | 2.7-2.93x | **3.68-3.83x** |
| `background_trickle` — Traditional | ~8.0s (baseline, unaffected before) | **25.2-25.8s** |
| `background_trickle` — FaaS | ~8.0s (baseline, unaffected before) | **10.8-11.3s** |

The medal-phase ratio improving to ~3.7-3.8x was expected and intended. The
**`background_trickle` blowup was not** — that phase's own event count and
time window were untouched by the edit, yet Traditional's completion time
for it more than tripled (8s → 25s+), while FaaS's grew far more mildly (8s
→ ~11s). Re-ran the full benchmark twice more to confirm this reproduces
before trusting it (it did, both times, in the same 25-26s / 11s range).

**Mechanism** (verified by the numbers, not just theorized): Traditional
runs every op — light state mutations and heavy CPU work alike — as threads
inside **one process sharing one GIL**. The reported medal-phase throughput
(150 calls in ~22s ≈ 147ms/call) exactly matches fully serial execution with
zero benefit from the 16-slot thread pool — confirming the GIL allows only
one thread's Python bytecode to run at any instant, regardless of how many
OS threads exist, when many of them are doing the same heavy CPU work. That
~22 seconds of near-total GIL monopolization is what starves every
*unrelated* concurrent request sharing that same process — background venue
bookings, shuttle dispatches, everything — pushing background_trickle's last
completions out to ~25s. FaaS degrades too (its subprocess calls compete for
the same 8 physical cores during the medal spike), but that's ordinary
OS-level preemptive scheduling across separate processes — inherently fairer
than one process's GIL locking out all other work — so the degradation is
far milder (8s → 11s, not 8s → 25s).

**Why this matters for the report**: this reframes the benchmark's headline
result. It's not just "FaaS is faster at CPU-bound work" (a raw-throughput
claim) — it's a **performance-isolation / noisy-neighbor** finding: in the
monolith, one heavy caller doesn't just run slowly itself, it silently
degrades every *unrelated* request sharing its process for the full duration
of that heavy work. FaaS's process-per-call model contains the damage to
ordinary core contention. This directly extends the report's existing
fault-isolation thesis (`bench/fault_isolation.py` already shows *crash*
isolation) into a parallel claim about *performance* isolation — arguably a
more compelling, more true-to-life "FaaS wins under stress" story than the
isolated CPU-phase number alone.

## 12. Current state / open question left for follow-up

- Current defaults: 648 events/architecture (~1,300 combined across both
  architectures per full run), ~40-43 seconds total wall time for both
  architectures together — still comfortably inside a "keep it short"
  budget.
- Correctness table, with locks/txn off (default): Traditional double-sells
  3/20 seats consistently; FaaS double-sells 19-20/20 consistently; the
  FaaS-side shuttle lost-update reproduced in most runs (opportunistic, not
  guaranteed, per the documented caveat). With `--lock --txn` both go to
  zero, confirming both architectures' "safe" mode is the same kind of
  global lock.
- Not yet resolved: whether to push `--scale` above 1.0 to reach a literal
  "thousands of total requests" figure. Given the newly discovered GIL
  starvation effect, pushing scale further would likely make Traditional's
  background-phase degradation grow *disproportionately* (more total
  GIL-monopolized CPU-seconds from more/heavier medal calls compounds the
  starvation tail), which could be either a good thing (bigger, more dramatic
  numbers) or could push total runtime past a comfortable budget — this
  tradeoff was raised with the user and, as of this writing, awaiting a
  decision on whether to lock in the current 150×2,000,000 configuration as
  final or scale further.

## Files added (all new; nothing pre-existing was modified)

- `bench/burst_workload.py`
- `bench/bounded_dispatch.py`
- `bench/mixed_burst.py`
- `bench/burst_chart.py`
- `results/mixed_burst/` (generated output directory: chart PNGs, JSON
  per-event record dumps from various runs — regenerate freely, not
  meant to be committed as fixed "results")
