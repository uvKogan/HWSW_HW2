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

= System Scenario & Thesis

We model the operations backend of an *Olympic Games Management System*: the
software that runs venues, ticketing, staffing, athlete services, live results,
and the medal table during a Games. Entity IDs are validated against a fixed
roster in `common/reference_data.py` (10 countries, 30 athletes, 15 volunteers,
12 real LA-2028 venues, 200 spectator users). The nine base operations are
`book_venue_slot` / `release_venue_slot`, `book_ticket` (reserve one *specific
seat*), `assign_volunteer`, `dispatch_shuttle`, `reserve_restaurant_table`,
`subscribe_to_updates` and `push_live_event` (a publish/subscribe pair), and
`update_country_score`; `go_live` is the Part 3 extension.

Our thesis is that *architecture acts as a forcing function*. We built the two
systems the way each is realistically built: the Traditional side as a *naive
monolith* — the path of least resistance when nothing forces structure — and
the FaaS side as the platform naturally guides you, one small function per file.
The comparison then shows where each model's defining traits help and hurt.
We keep the axes Traditional genuinely wins (per-call latency, state growth,
atomic cross-cutting change), but the overall balance favors FaaS: it wins
parallel throughput, crash resilience, idle cost, *and* prevents a whole class
of bug by construction. The two builds are now *independent implementations*
(no shared business logic), each validated by its own unit tests
(`common/test_operations.py`, `Traditional/test_monolith.py`); they still agree
byte-for-byte on a 2000-event sequential replay.

= Part 1 — Traditional Architecture (naive monolith)

The Traditional build is the *entire system in one file* (`Traditional/server.py`,
~300 lines): all state in module-level global dicts, every operation inlined into
one giant `handle()` dispatcher, validation copy-pasted at each call site, magic
numbers inline, and a stdlib `ThreadingHTTPServer` on top. Nothing here is
factored or reused — it grew, as monoliths do. Its defining traits:
*shared mutable memory* (state access is O(1) and multi-step changes are
naturally atomic) and *one long-lived process*. Those traits are also its
weaknesses: the process is a single point of failure holding all state in memory
with *no persistence*, it is GIL-bound to ~one CPU core, and its shared memory
invites concurrency bugs. We left one such bug in, documented: the "current
request's actor" is stashed in a module global `_CTX` and read back when
recording a seat's buyer. Correct single-threaded; under the threaded server two
overlapping requests clobber `_CTX`, so a seat is silently recorded against the
*wrong* buyer (Part 4f).

= Part 2 — FaaS Architecture (decoupled)

The FaaS build decomposes the system into independent functions
(`FaaS/functions/<op>.py`), one per operation, each a four-line shim over a small
pure function in `common/operations.py` — the decoupled core the one-function-
per-file boundary *led us* to factor out. A gateway (`gateway.py`) simulates the
platform's event router: each call spawns a *fresh Python subprocess* with no
shared memory. Because functions are stateless, state lives outside the process
in sqlite (`storage.py`), reloaded and saved per call via a runtime shim
(`_runtime.py`). Defining traits: *isolation* and *statelessness* — each call is
sandboxed and independently scalable, and there is no shared memory to corrupt or
long-lived process to lose — at the cost of an external state round-trip and lost
cross-call atomicity.

= Part 3 — Feature Extension & Ease of Change

The new feature, `go_live`, is a cross-cutting cascade fired when a match starts:
announce to subscribers → put a broadcast stream on air → recompute the medal
standings. *Which model is easier to extend depends on the change:*

- *Cross-cutting atomic change (`go_live`) → Traditional wins.* In the monolith
  it is one more branch calling the others in-process, atomic for free. In FaaS
  it is either a fat function that violates the one-responsibility principle, or
  an orchestrator chaining three `invoke()`s with *no transaction spanning them*
  (`orchestrators/go_live_chain.py`): a crash after step 2 leaves the match live
  and streaming but standings stale — a partially-applied state Traditional
  cannot reach.
- *Independent new capability → FaaS wins.* Adding an isolated operation (e.g.
  `render_highlight`) in FaaS is *one new file, zero edits to existing code*, and
  deploys/scales on its own. In the monolith the same change means editing the
  shared `handle()` and the global state — touching the one file everything
  depends on, risking every other operation, and redeploying the whole process.

= Part 4 — Performance, Resilience & Correctness

Measured on an 8-core Linux host (Python 3.12.3, `perf`/linux-tools 6.8). Six
axes; the two models' defining traits flip the winner by workload.

*(a) Per-call overhead — base 2000-event workload.* FaaS pays for a fresh
interpreter and a sqlite round-trip on every call; the monolith is an in-process
call. `perf stat` follows forked children, so the FaaS figures aggregate all
2000 spawned processes:

#table(
  columns: (auto, auto, auto, auto),
  align: (left, right, right, right),
  [*Metric*], [*Traditional*], [*FaaS*], [*FaaS/Trad*],
  [Wall-clock (s)], [0.187], [239.56], [1281×],
  [CPU cycles], [459.6 M], [487.3 B], [1060×],
  [Instructions], [775.6 M], [767.3 B], [989×],
  [Context switches], [1], [19,983], [19,983×],
  [Page faults], [3,203], [4,302,009], [1343×],
)

The ~20,000× context-switch and 1343× page-fault blowup *is* the process-spawn
cost made visible: 2000 interpreter starts and teardowns versus one.

*(b) Latency under state growth — Traditional wins.* Replaying at increasing
sizes, FaaS reloads and reserialises the whole (growing) state blob every call,
so per-call cost rises and total work is roughly O(N²); the monolith keeps state
in memory and stays flat — its per-call cost even *drops* as fixed startup
amortises. Watch the ratio climb with N:

#table(
  columns: (auto, auto, auto, auto, auto),
  align: (right, right, right, right, right),
  [*Events*], [*Trad (s)*], [*FaaS (s)*], [*Ratio*], [*Trad µs/call*],
  [250], [0.118], [23.9], [204×], [471],
  [500], [0.140], [48.9], [349×], [281],
  [1000], [0.125], [100.9], [809×], [125],
  [2000], [0.145], [209.1], [1444×], [72],
)

*(c) Parallel throughput on independent CPU — FaaS wins.* 32 independent
`project_medals` calls (3 M iterations each) on 8 cores: Traditional *36.51 s*,
FaaS *2.70 s* — a *13.5× FaaS win*. The monolith is one GIL-bound process pinned
to ~one core; FaaS runs a process per call and uses all 8.

*(d) Fault isolation — FaaS wins.* One poison `render_highlight` call hits a
native-level crash (`os.abort()`, SIGABRT — a segfault/OOM class failure). In the
monolith it kills the single process: the server dies, all in-memory state is
lost, every other request fails (blast radius = whole system). In FaaS it kills
only that one subprocess; the gateway catches it, later calls keep working, and
every previously-persisted seat survives (blast radius = one request).

*(e) Idle footprint — FaaS wins.* The monolith is a long-lived process holding
*20.1 MB* resident while completely idle; FaaS scales to zero — *0 MB, no process*
between calls, materialising one for ~100 ms only while a call runs.

*(f) Cross-request state leak — FaaS wins by construction.* 40 concurrent
bookings, each a distinct seat and distinct user (no seat contention). The
monolith's shared `_CTX` global is clobbered across threads, recording *34 of 40*
seats against the wrong buyer. FaaS records *0* wrong: a process-per-call model
has no shared request context to leak — the bug is impossible, not merely
avoided. (A coarse lock would also mask it in the monolith; the point is the
architecture that never has the hazard.)

*Reading the results.* The monolith wins where work is small, sequential, and
stateful (a, b) — in-memory state and no spawn cost are hard to beat, and a
well-engineered monolith would keep those wins. But its single shared process is
also its liability: it cannot use multiple cores (c), one crash takes everything
down (d), it costs memory around the clock (e), and its shared memory invites
correctness bugs the isolated model cannot have (f). FaaS trades per-call
efficiency for isolation, elasticity, and enforced structure — and on balance
that trade wins.

= AI Tool Usage Disclosure

We used an AI assistant (Claude Code) throughout, and disclose it fully.
*Architectural discussion:* the assistant helped design the "architecture as a
forcing function" comparison — in particular the naive-monolith-vs-decoupled-FaaS
framing and the six evaluation axes, including the ones where FaaS wins
decisively (fault isolation, idle cost, the cross-request leak) and the ones we
keep honest for Traditional (per-call latency, state growth, atomic change).
*Implementation:* it wrote much of the scenario code, the naive monolith, the
benchmarks, and this report scaffold under our direction; we chose the scenario,
the operations, the seat-level model, the feature, and the FaaS-favored tilt.
*Verification:* every number here was produced by running the code on our own
8-core Linux host, not asserted by the model. A verbatim prompt log is in
`prompts.md` and a curated summary in `PROJECT.md`.
