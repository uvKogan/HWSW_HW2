// HW2 report -- max 6 pages. Compile with: typst compile report.typ report.pdf
#set page(margin: 1.4cm, numbering: "1")
#set text(size: 10pt)
#set par(justify: true)
#show heading.where(level: 1): it => text(size: 12pt, weight: "bold")[#it]

#align(center)[
  #text(size: 15pt, weight: "bold")[Traditional Software Design vs Function-as-a-Service] \
  #text(size: 12pt)[An Olympic Games Management System, Built Twice] \
  #text(size: 9pt)[Matan Cohen · Yuval Kogan]
]

= System Scenario


We model the operations backend of an *Olympic Games Management System*:
the software that runs venues, ticketing, staffing, athlete services, live
results, and the medal table during a Games. All logic lives in one shared
module (`common/operations.py`), so both architectures execute *identical*
business code and differ only in their execution model. Entity IDs are
validated against a fixed roster in `common/reference_data.py` (10 countries,
30 athletes, 15 volunteers, 12 real LA-2028 venues, 200 spectator users).

The system implements nine base operations (Parts 1 & 2):
`book_venue_slot` / `release_venue_slot` (reserve a venue for a session),
`book_ticket` (reserve one *specific seat* for a match), `assign_volunteer`,
`dispatch_shuttle` (board passengers against a seat ceiling),
`reserve_restaurant_table`, `subscribe_to_updates` and `push_live_event` (a
publish/subscribe pair that fans a live update out to a match's subscribers),
and `update_country_score` (medal tally). A tenth operation, `go_live`, is the
Part 3 extension, and an eleventh, `project_medals`, drives the parallel
benchmark.

= Part 1 — Traditional Architecture

The traditional build (`Traditional/`) is a monolith: one long-lived process
holding all state in a single in-memory dictionary (`services/__init__.py`),
exposed through a stdlib `http.server` (`ThreadingHTTPServer`, no framework).
A request `POST /invoke {"op": ..., "params": ...}` is dispatched by a direct
in-process function call — `OPERATIONS[op](STATE, params)` — with no
serialization boundary between the service layer and the business logic. A
second mode replays a workload file in-process for measurement. The defining
traits are *shared mutable memory* and *one process*: state access is O(1) and
a multi-step change is naturally atomic, but the single process is also a
single point of failure and, under Python's GIL, a single CPU core for
CPU-bound work.

= Part 2 — FaaS Architecture

The FaaS build (`FaaS/`) decomposes the system into independent functions
(`functions/<op>.py`), one per operation. A gateway (`gateway.py`) simulates
the platform's event router: each operation call spawns a *fresh Python
subprocess* with no shared memory (`subprocess.run`). Because functions are
stateless, state lives outside the process in sqlite (`storage.py`), reloaded
and saved on every invocation via a thin runtime shim (`functions/_runtime.py`)
— the analogue of a cloud provider's Lambda wrapper. The functions have zero
dependencies on one another. The defining traits are *isolation* and
*statelessness*: each call is sandboxed and independently scalable, but state
must round-trip through an external store on every call and cross-call
atomicity is lost.

Both builds are driven by the same deterministic workload
(`common/workload.py`); `common/compare_states.py` confirms they reach an
identical final state (`MATCH`). Because both run the same operations module,
that gate can only catch *architecture* divergence, so `common/test_operations.py`
separately checks the business logic (8 unit tests).

= Part 3 — Feature Extension: `go_live`

The new feature is a cross-cutting "go live" cascade fired when a match
starts: (1) `push_live_event` announces it and fans out to subscribers, (2) a
broadcast stream is put on air, (3) the medal `standings` are recomputed. It
deliberately touches four state regions in one business transaction, to expose
how each architecture copes with a change that spans functions.

*Traditional:* trivial. `go_live` is one more function calling three others
in-process; `dispatch()` already routes any registered op, so *zero files and
zero infrastructure change* — and the three steps are atomic for free.

*FaaS:* two options, both revealing. A *naive* port
(`functions/go_live.py`) bundles all three steps behind a single load/save —
it works but quietly violates the "independent, isolated" principle (one fat
function). The *idiomatic* version (`orchestrators/go_live_chain.py`) chains
three separate `invoke()` calls — but that means three subprocess spawns and
three sqlite round-trips with *no transaction spanning them*. A crash after
step 2 leaves the match live and streaming but the standings stale — a
partially-applied state the Traditional single call can never reach.

*Verdict:* the Traditional monolith is far easier and safer to extend with a
cross-cutting feature; FaaS forces a choice between violating its own
isolation principle or rebuilding the atomicity it lost (sagas, compensation,
idempotency keys). More parts change, and the change is riskier.

= Part 4 — Performance Evaluation

Measured on an 8-core Linux host (Python 3.12.3, `perf`/linux-tools 6.8).
`perf stat` follows forked children, so FaaS figures aggregate all spawned
processes. The comparison has four axes; the two architectures' defining
traits flip the winner by workload.

*(a) Per-call overhead — base 200-event workload.* FaaS pays for a fresh
interpreter and a sqlite round-trip on every call:

#table(
  columns: (auto, auto, auto, auto),
  align: (left, right, right, right),
  [*Metric*], [*Traditional*], [*FaaS*], [*FaaS/Trad*],
  [Wall-clock (s)], [0.125], [19.24], [154×],
  [CPU cycles], [342.7 M], [47.20 B], [138×],
  [Instructions], [490.8 M], [64.78 B], [132×],
  [Context switches], [5], [3,154], [631×],
  [Page faults], [2,612], [321,810], [123×],
)

The 631× context-switch and 123× page-fault blowup *is* the process-spawn cost
made visible: 200 interpreter starts and teardowns versus one.

*(b) Latency under state growth.* Replaying the workload at increasing sizes,
FaaS reloads and reserialises the whole (growing) state blob every call, so
per-call cost rises and total work is roughly O(N²); Traditional keeps state
in memory and stays flat:

#table(
  columns: (auto, auto, auto, auto),
  align: (right, right, right, right),
  [*Events*], [*Traditional (s)*], [*FaaS (s)*], [*Ratio*],
  [100], [0.134], [8.70], [65×],
  [500], [0.153], [44.64], [291×],
  [1000], [0.128], [92.16], [718×],
  [2000], [0.169], [212.64], [1258×],
)

*(c) Parallel throughput on independent CPU work — FaaS wins.* 16 independent
`project_medals` calls (3 M iterations each) on 8 cores: Traditional
*12.45 s*, FaaS *2.13 s* — a *5.86× FaaS win*. The monolith is one
process, so the GIL serialises CPU-bound work onto ~one core; FaaS runs a
process per call and actually uses all 8 cores.

*(d) Consistency under contention — Traditional wins.* 30 users race for 10
seats. Unprotected, both oversell (Traditional 4 double-sold seats, FaaS 8 —
worse, because its race spans whole processes). The fix costs differ sharply:
Traditional needs *one* in-process `threading.Lock`; FaaS needs a
`BEGIN IMMEDIATE` transaction spanning load→op→save, and since state is a
single JSON blob, that lock is effectively *global*, not per-seat.

*Why it makes sense.* FaaS trades per-call efficiency and shared-state
consistency for isolation and independent parallelism. When work is
independent and CPU-bound (c), that isolation is a decisive advantage; when
work is small, stateful, or contended (a, b, d), the constant cost of
spawning a process and shipping state externally dominates and the monolith
wins by two to three orders of magnitude.

= AI Tool Usage Disclosure

We used an AI assistant (Claude Code) throughout, and disclose it fully.
*Architectural discussion:* the assistant helped shape the shared-core design
(one operations module, two dispatch layers) so the comparison isolates the
execution model, and helped design the four-axis thesis — in particular
steering us to include a workload where FaaS *wins* (parallel CPU) rather than
a one-sided result. *Implementation:* it wrote much of the scenario code, the
two benchmarks, and this report scaffold under our direction; we chose the
scenario, the operation set, the seat-level ticketing model, and the feature.
*Verification:* every result here was produced by running the code
(`./script.sh`, the benchmarks) on our own hardware, not asserted by the model.
A verbatim prompt log is in `prompts.md` and a curated summary in `PROJECT.md`.
