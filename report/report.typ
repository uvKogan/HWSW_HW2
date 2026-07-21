// HW2 report -- max 6 pages. Compile with: typst compile report.typ report.pdf
#set page(margin: 1.3cm, numbering: "1")
#set text(size: 9.7pt)
#set par(justify: true)
#show heading.where(level: 1): it => text(size: 12pt, weight: "bold")[#it]
#show heading.where(level: 2): it => text(size: 10.3pt, weight: "bold")[#it]
#show link: set text(fill: rgb("#14477d"))

#align(center)[
  #box(image("fig/la28.png", width: 1.6cm))

  #text(size: 15pt, weight: "bold")[Traditional Software Design vs Function-as-a-Service] \
  #text(size: 12pt)[An Olympic Games Management System, Built Twice] \
  #text(size: 9pt)[Matan Cohen · Yuval Kogan]
]

= System Scenario & Thesis

*It is the evening of the 100 m final at the LA 2028 Games.* Inside the stadium a
volunteer scans the last of 80,000 ticket-holders to their exact seats; outside,
shuttles ferry athletes between the village and twelve venues; in a control room
the medal table flips the instant the photo-finish is confirmed, and the result
reaches millions of second-screen fans a heartbeat later. Then the gun goes off,
and the entire crowd refreshes at once. Behind all of it sits one *operations
backend* (which, for some reason, two students wrote for a homework assignment,
and since it was free the Olympic committee decided to use it): the software that
runs venues, ticketing, staffing, athlete services, live results, and the medal
table. We build that backend *twice*, once as a
traditional monolith and once as a set of serverless functions, and let the
Games' own workload decide which architecture holds up. (We come back to this
100 m-final night in #link(<ax-c2>)[§4(c2)], when the whole stadium hits the system at once.)

The system is grounded in a fixed roster (`common/reference_data.py`): 10
countries, 30 athletes, 15 volunteers, 12 real LA-2028 venues, and 200 spectator
users, so every ID validates against real data rather than a free-floating
string. Its twelve operations:

- *`book_venue_slot` / `release_venue_slot`*: claim or free a venue for a match; a
  venue holds one match at a time, so a double-booking is rejected.
- *`book_ticket`*: reserve one *specific numbered seat* for a spectator; a seat
  already sold is refused (the seat-level model that makes the #link(<ax-f>)[§4(f)] leak concrete).
- *`assign_volunteer`*: roster a volunteer to a venue for the day.
- *`dispatch_shuttle`*: send a shuttle on a village→venue route with a seat capacity.
- *`reserve_restaurant_table`*: seat an athlete's party (bounded size) in a village
  dining hall.
- *`subscribe_to_updates` / `push_live_event`*: a publish/subscribe pair; fans
  subscribe to a match topic and start/score/finish events fan out to every subscriber.
- *`update_country_score`*: award a gold/silver/bronze to a country and roll the
  medal standings up.
- *`go_live`* (Part 3): a cross-cutting cascade fired when a match starts (announce
  to subscribers → stream on air → recompute standings).
- *`render_highlight`*: render a match highlight reel; a corrupted input triggers a
  native crash, our fault-injection probe (#link(<ax-d>)[§4(d)]).
- *`project_medals`*: a CPU-bound, read-only medal *forecast* (a simplified
  Monte-Carlo, many fixed-probability trials rather than a full statistical model),
  touching no state; the embarrassingly-parallel workload behind #link(<ax-c>)[(c)] and #link(<ax-c2>)[(c2)].

Our thesis is that *architecture acts as a forcing function*. We built the two
systems the way each is realistically built: the Traditional side as a *naive
monolith*, the path of least resistance when nothing forces structure, and
the FaaS side as the platform naturally guides you, one small function per file.
The comparison then evaluates the four dimensions the assignment asks about
(performance, extensibility, maintainability, and security) and shows where each
model's defining traits help and hurt. Traditional genuinely wins on per-call
latency, state growth, and atomic cross-cutting change; FaaS wins on parallel
throughput, load-spike resilience, crash and performance isolation, and idle
cost, *and* prevents a whole class of bug by construction, so on balance FaaS
comes out ahead. The two builds are *independent implementations* (no shared business
logic), each validated by its own unit tests; they still agree byte-for-byte on
a 2000-event replay.

= Part 1: Traditional Architecture (naive monolith)

The Traditional build is the *entire system in one file* (`Traditional/server.py`,
~300 lines): all state in module-level global dicts, every operation inlined into
one giant `handle()` dispatcher, validation copy-pasted at each call site, magic
numbers inline, and a stdlib `ThreadingHTTPServer` on top. Nothing is factored or
reused; it grew, as monoliths do. Its defining traits: *shared mutable memory*
(state access is O(1) and multi-step changes are naturally atomic) and *one
long-lived process*. Those traits are also its weaknesses: the process is a
single point of failure holding all state in memory with *no persistence*, it is
GIL-bound to ~one CPU core, and its shared memory invites concurrency bugs. We
left one such bug in, documented: the "current request's actor" is stashed in a
module global `_CTX` and read back when recording a seat's buyer. Correct
single-threaded; under the threaded server two overlapping requests clobber
`_CTX`, so a seat is silently recorded against the *wrong* buyer (#link(<ax-f>)[§4(f)]).

= Part 2: FaaS Architecture (decoupled)

The FaaS build decomposes the system into independent functions
(`FaaS/functions/<op>.py`), one per operation, each a four-line shim over a small
pure function in `common/operations.py`, the decoupled core the one-function-
per-file boundary *led us* to factor out. A gateway (`gateway.py`) simulates the
platform's event router: each call spawns a *fresh Python subprocess* with no
shared memory (a faithful stand-in for a cold Lambda invocation). Because
functions are stateless, state lives outside the process in sqlite
(`storage.py`), reloaded and saved per call via a runtime shim (`_runtime.py`).
Defining traits: *isolation* and *statelessness*. Each call is sandboxed and
independently scalable, and there is no shared memory to corrupt or long-lived
process to lose, at the cost of an external state round-trip and lost cross-call
atomicity.

= Part 3: Feature Extension & Ease of Change

The new feature, `go_live`, is a cross-cutting cascade fired when a match starts:
announce to subscribers → put a broadcast stream on air → recompute the medal
standings. *Which model is easier to extend depends on the change:*

- *Cross-cutting atomic change (`go_live`) → Traditional wins.* In the monolith
  it is one more branch calling the others in-process, atomic for free. In FaaS
  it is either a fat function that violates the one-responsibility principle, or
  an orchestrator chaining three `invoke()`s with *no transaction spanning them*
  (`orchestrators/go_live_chain.py`): a crash after step 2 leaves the match live
  and streaming but standings stale, a partially-applied state Traditional
  cannot reach.
- *Independent new capability → FaaS wins.* Adding the isolated `render_highlight`
  operation in FaaS was *one new 4-line file, zero edits to existing code*, and it
  deploys and scales on its own. In the monolith the same capability means editing
  the shared `handle()` and the global state, touching the one file every other
  operation lives in, risking all of them, and redeploying the whole process.

= Part 4: Evaluation

== Methodology

*Hosts.* The primary host is *naranja14* (Technion CS lab): an 8-vCPU
QEMU/KVM guest, Linux 5.15, Python 3.10.12, `perf`. We cross-checked on a second
8-core host (Python 3.12.3, `perf`/linux-tools 6.8). Reporting the guest as
primary is deliberate; it also lets us document a real `perf`-in-a-VM pitfall
(§4g).

*Workload.* One deterministic, seeded generator (`common/workload.py`, seed 42)
emits the base operations with IDs drawn from bounded reference-data pools, so
entities collide realistically (seats resold, standings accumulate) rather than
every call touching a fresh ID. Both architectures replay the *identical* event
stream, so any difference is the execution model, not the input.

*Instrumentation.* Hardware counters via `perf stat` (which follows forked
children, so FaaS figures aggregate all spawned processes); wall-clock via
`time.perf_counter`; resident memory via `/proc/<pid>/status` `VmRSS`;
concurrency driven by a `ThreadPoolExecutor` firing simultaneous requests; and a
native crash injected with `os.abort()`. Each benchmark is a standalone module
under `bench/` and is wired into `script.sh`.

*Correctness & variance.* The two sides are *independent* implementations, each
validated on its own: `common/test_operations.py` (8 tests over the FaaS core)
and `Traditional/test_monolith.py` (10 tests over the monolith, including that
single-threaded booking attributes correctly; the #link(<ax-f>)[§4(f)] bug is concurrency-only).
`common/compare_states.py` confirms the two structurally different builds still
produce matching final states after the replay. Effects below span one-to-three
orders of magnitude, so one representative run suffices and the *ratios*, not the
absolute times, are the claim.

== Results: eight axes

The two models' defining traits flip the winner by workload. Scorecard first,
then each axis in detail:

#table(
  columns: (auto, auto, auto),
  align: (left, center, left),
  inset: 4pt,
  [*Axis*], [*Winner*], [*Margin (primary host)*],
  [(a) Per-call overhead], [Traditional], [2683× faster wall-clock],
  [(b) Latency under state growth], [Traditional], [up to 2740× faster],
  [(c) Parallel independent CPU], [*FaaS*], [7.6× (13.5× on bare metal)],
  [(c2) Spike / load under pressure], [*FaaS*], [4.9× throughput, 24× lower p99],
  [(d) Fault isolation], [*FaaS*], [all state lost vs. 0 lost],
  [(e) Idle footprint], [*FaaS*], [17.4 MB resident vs. 0],
  [(f) Cross-request leak], [*FaaS*], [39/40 wrong vs. 0 wrong],
  [(h) Perf. isolation (noisy neighbor)], [*FaaS*], [194× latency spike vs. none],
)

*(a) Per-call overhead: base 2000-event workload.*<ax-a> FaaS pays for a fresh
interpreter and a sqlite round-trip on every call; the monolith is one
in-process call.

#table(
  columns: (auto, auto, auto, auto),
  align: (left, right, right, right),
  inset: 4pt,
  [*Metric*], [*Traditional*], [*FaaS*], [*FaaS/Trad*],
  [Wall-clock (s)], [0.145], [388.99], [2683×],
  [CPU cycles], [316.8 M], [265.2 B], [837×],
  [Instructions], [552.9 M], [284.9 B], [515×],
  [Context switches], [0], [52,153], [n/a],
  [Page faults], [3,144], [4,771,317], [1518×],
)

The context-switch and page-fault blow-up *is* the process-spawn cost made
visible: 2000 interpreter starts and teardowns versus one long-lived process.

*(b) Latency under state growth: Traditional wins.* Replaying at increasing
sizes, FaaS reloads and reserialises the whole (growing) state blob every call,
so per-call cost rises and total work is roughly O(N²); the monolith keeps state
in memory and stays flat; its per-call cost even *drops* as fixed startup
amortises. Watch the ratio climb with N:

#table(
  columns: (auto, auto, auto, auto, auto),
  align: (right, right, right, right, right),
  inset: 4pt,
  [*Events*], [*Trad (s)*], [*FaaS (s)*], [*Ratio*], [*Trad µs/call*],
  [250], [0.084], [39.8], [472×], [337],
  [500], [0.093], [77.6], [831×], [187],
  [1000], [0.103], [187.7], [1824×], [103],
  [2000], [0.136], [372.0], [2740×], [68],
)

*(c) Parallel throughput on independent CPU: FaaS wins.*<ax-c> 32 independent
`project_medals` calls (3 M iterations each) on 8 vCPUs: Traditional *26.9 s*,
FaaS *3.5 s*, a *7.6× FaaS win* on the KVM guest (and *13.5×* on the bare
8-core cross-check host, where scheduling overhead is lower). The monolith is
one GIL-bound process pinned to ~one core; FaaS runs a process per call and uses
every core.

*(c2) Spike / load under pressure: FaaS wins.*<ax-c2> Back to the 100 m final: the gun
fires, the result posts, and the whole stadium refreshes the live standings in
the same second. That is the "DoS it and watch it degrade" test. We ramp
simultaneous clients 8→512 and fire a 512-request burst of `project_medals`
(200k iters) at each level, recording the latency distribution and sustained
throughput rather than just a total.

#table(
  columns: (auto, auto, auto, auto, auto),
  align: (right, right, right, right, right),
  inset: 4pt,
  [*Clients*], [*Trad req/s*], [*Trad p99 (s)*], [*FaaS req/s*], [*FaaS p99 (s)*],
  [8], [17.3], [0.9], [89.8], [0.1],
  [64], [17.5], [4.2], [86.4], [1.2],
  [256], [17.6], [15.0], [86.7], [1.1],
  [512], [17.5], [28.8], [86.5], [1.2],
)

The monolith's throughput is *pinned at \~17.5 req/s across the entire 8→512
range* (it never scales), while its p99 tail latency grows linearly with the
backlog (0.9 s → *28.8 s*) as every request queues behind one core. FaaS holds
\~87 req/s with bounded \~1 s tail latency. *At peak: 4.9× throughput, 24× lower
p99.* One might object that under load the CPU meter shows *all* cores busy, not
one core pinned, but a direct measurement shows the monolith consumes only
*1.02 of 8 cores*: the Linux scheduler merely migrates the single GIL-holding
thread across cores, so each per-core bar reads \~13% instead of one at 100%.
The flat throughput (\~8× lower than a true multicore server) and the 1.02-core
aggregate are the ground truth; the even-looking bars are migration, not
parallelism.

#figure(
  image("fig/htop_output.png", width: 92%),
  caption: [`htop` during the spike. All eight per-core bars sit at 8–19% (none
    pinned), which *looks* parallel, yet the `Traditional.server` process reads
    *101% CPU* and the load average is *0.96*: exactly one core's worth of work,
    migrated across all eight cores rather than eight cores running in parallel.],
)

*(d) Fault isolation: FaaS wins.*<ax-d> One poison `render_highlight` call hits a
native-level crash (`os.abort()`, SIGABRT, a segfault/OOM class failure). In the
monolith it kills the single process: the server dies, all in-memory state is
lost, every other request fails (blast radius = whole system). In FaaS it kills
only that one subprocess; the gateway catches it, later calls keep working, and
all 8 previously-persisted seats survive (blast radius = one request).

*(e) Idle footprint: FaaS wins.* The monolith is a long-lived process holding
*17.4 MB* resident while completely idle; FaaS scales to zero: *0 MB, no process*
between calls, materialising one for ~44 ms only while a call runs.

*(f) Cross-request state leak: FaaS wins by construction.*<ax-f> 40 concurrent
bookings, each a distinct seat and distinct user (no seat contention). The
monolith's shared `_CTX` global is clobbered across threads, recording *39 of 40*
seats against the wrong buyer. FaaS records *0* wrong: a process-per-call model
has no shared request context to leak; the bug is impossible, not merely
avoided. (A coarse lock would also mask it; the point is the architecture that
never has the hazard.)

*(h) Performance isolation under a realistic mixed load: FaaS wins.*<ax-h> Every
axis above isolates one variable and fires it all at once. `bench/mixed_burst.py`
instead replays a timestamped, narrative-shaped "Games day" (648 events over
seven phases: background traffic, a streaming peak, a ticket rush, a
shuttle-boarding race, and a CPU-bound medal-projection spike) through a paced,
concurrency-capped dispatcher, so the load resembles real bursty traffic rather
than a synthetic flood. Two findings on naranja14. First, the CPU-bound spike,
now embedded in the mix, still favours FaaS decisively: 150 independent
projections take *84.4 s* on the monolith (one GIL-bound core) versus *12.2 s* on
FaaS (a process per call across 8 vCPUs), a *6.9× win*. Second, the headline:
during that 84 s spike, unrelated light background requests sharing the monolith's
process are *starved*, their median latency jumping from *2.7 ms* to *527 ms*
(*194×*, tail 3.9 s) purely because one heavy caller monopolises the GIL. In FaaS
the same background requests are untouched (0.3×): each call is its own process,
so a heavy neighbour cannot steal their CPU. This extends fault isolation
(#link(<ax-d>)[§4(d)]) from *crashes* to *performance*, in the monolith one heavy
caller silently degrades every unrelated request; FaaS contains the blast radius.

The honest counterweight is the same overhead as #link(<ax-a>)[§4(a)]: for cheap,
high-frequency state ops, FaaS's per-call subprocess + sqlite tax makes it far
slower per operation (the ticket-rush phase: Traditional *0.5 s* vs FaaS
*22.9 s*). The mixed test shows both truths at once, so it is evidence for the
balance, not a one-sided win.

Sweeping the medal phase's per-call cost turns the isolation gap into a scaling
law. As the heavy phase grows, the monolith's *unrelated* background work climbs
right along with it, all the way to *87 s*, because the medal spike monopolises
the shared GIL; FaaS stays flat and immune, each call being its own process. The
two lines cross near 1 M iterations: FaaS is the slower baseline (its per-op tax)
but, because it never degrades, past the crossover it wins outright on isolation
alone.

#figure(
  image("fig/sweep_noisy_neighbor.png", width: 100%),
  caption: [Sweeping the medal phase's per-call cost (naranja14). Left: the
    CPU-bound phase, where FaaS's parallel win grows with load (1.6× to 7.1×).
    Right: completion time of *unrelated* background work, rising on the monolith
    (starved as the spike monopolises the GIL) but flat on FaaS (isolated); the
    lines cross near 1 M iterations.],
)

== Where the cycles go (flamegraphs)

*(g)*<ax-g> CPython's `perf` trampoline (`-X perf`) makes `perf` resolve Python-level
frames, so a cycle-attributed flamegraph shows *what* each model spends cycles
on, not merely how many. The split is stark (ranges span the two hosts):

#table(
  columns: (auto, auto, auto),
  align: (left, right, right),
  inset: 4pt,
  [*Share of CPU cycles*], [*Traditional*], [*FaaS*],
  [Business-logic operations], [73–93%], [≈ 0%],
  [Import + process spawn + dynamic link], [< 1%], [40–72%],
  [sqlite / external-state I/O], [0%], [4–22%],
)

FaaS burns essentially *all* its cycles on infrastructure, re-importing the
interpreter and touching sqlite on every call, with the operation itself a sliver
too thin to see; the monolith, by contrast, spends its cycles on the actual work.
The FaaS flamegraph makes it visual (both full interactive SVGs are in
`results/flamegraphs/`):

#figure(
  image("fig/fg_faas.png", width: 98%),
  caption: [FaaS: the width is dominated by wide interpreter-import / process-spawn
    plateaus, and the real operation is the invisible sliver on top. The monolith's
    flamegraph (in the repo) is the mirror image: many narrow business-logic towers,
    the actual work.],
)

This is the mechanism *behind* the aggregate blow-up in #link(<ax-a>)[(a)].

*A `perf`-in-a-VM gotcha (primary host).* On the KVM guest, `perf stat` counts
correctly but `perf record -F 999` captured *zero* samples: the slow virtual-PMU
overflow interrupt made the kernel throttle `perf_event_max_sample_rate` toward
zero, starving frequency mode. The fix is a *fixed sampling period*
(`perf record -c 2000000`) plus `--call-graph dwarf`, since CPython carries no
frame pointers.

== Reading the results (and threats to validity)

The monolith wins where work is small, sequential, and stateful (a, b):
in-memory state and no spawn cost are hard to beat. Its single shared process is
also its liability: it cannot use multiple cores (c), one crash takes everything
down (d), it costs memory around the clock (e), and its shared memory invites
correctness bugs the isolated model cannot have (f). Three honesty caveats: the
monolith is a *naive first draft* (the structure a team ends up with when
nothing forces otherwise), and a well-engineered one would keep the (a,b) wins,
though FaaS makes that good structure the default rather than a discipline; the
work is *pure Python*, so the GIL is what makes the parallel gap in (c) so wide
(native threads would narrow it, but the "one process ≈ one core" limit is real);
and the KVM guest's scheduling overhead *understates* (c) versus bare metal.

= Maintainability & Security

Beyond raw performance, the structural differences carry directly into the
assignment's other two dimensions. *Maintainability:* the FaaS decomposition is
testable in isolation (one pure function per file), independently deployable, and
bounds the blast radius of a change to a single function; the monolith's one
`handle()` means every edit risks every operation and forces a whole-process
redeploy. *Security:* isolation gives each FaaS function its own process and a
natural least-privilege boundary: a compromised or buggy function cannot read
the whole system's in-memory state, and indeed the #link(<ax-f>)[§4(f)] leak is a
*confidentiality* failure (one user's identity bleeding into another's record)
that only exists because the monolith shares one memory space across all
requests. The honest counterweight is that FaaS enlarges the surface to secure:
many independent entry points and an external state store, trading one hardened
process for a distributed system to lock down. A fuller confidentiality analysis
(formal threat modeling, data-flow isolation between functions, per-function
least-privilege scoping of the shared state store) fell outside this assignment's
scope; we surface the #link(<ax-f>)[§4(f)] leak as concrete evidence that the axis
matters and flag the deeper treatment as worthwhile future work, not something we
claim to have settled here.

= AI Tool Usage Disclosure

We used an AI assistant (Claude Code) throughout, and disclose it fully. \
*Architectural discussion:* the "architecture as a forcing function" comparison
(the naive-monolith-vs-decoupled-FaaS framing) was our idea; the assistant
helped us keep it in mind through implementation, holding the monolith and the
decoupled-FaaS structures consistent with that framing and helping shape the
evaluation axes (parallel throughput, fault isolation, idle cost, the
cross-request leak, and where Traditional stays ahead on per-call latency, state
growth, and atomic change).\
 *Implementation:* it wrote much of the scenario code,
the naive monolith, the benchmarks, and this report scaffold under our direction;
we chose the scenario, the operations, the seat-level model, and the feature. \
*Debugging & profiling:* it set up the `perf`/flamegraph
toolchain on both hosts and produced the flamegraphs; together we diagnosed the
KVM sampling failure in #link(<ax-g>)[§4(g)], tracing zero-sample `perf record` to sample-rate
throttling of a slow virtual PMU interrupt, fixed with a fixed-period capture. \
*Verification:* every number here was produced by running the code on our own
hardware (two Linux hosts), not asserted by the model. A verbatim prompt log is
in `prompts.md` and a curated summary in `PROJECT.md`.
