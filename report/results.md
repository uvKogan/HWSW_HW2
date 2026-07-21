# Part 4 — Measured Results

**Primary host — `naranja14` (Technion CS lab):** 8-vCPU QEMU/KVM guest,
Linux 5.15, **Python 3.10.12**, `perf`. **Cross-check host:** an 8-core box
(kernel 7.1.0-rc1, **Python 3.12.3**, `perf`/linux-tools 6.8). All numbers below
are from naranja14 unless labelled "cross-check". Reproduce with `./script.sh`
or the individual `python3 -m bench.*` commands.

Balanced but FaaS-favored: Traditional wins the two sequential/stateful axes
(a, b); FaaS wins the four isolation/elasticity/correctness axes (c, d, e, f).

## (a) Per-call overhead — base 2000-event workload (`perf stat`)

`perf stat` follows forked children, so FaaS aggregates all 2000 spawned processes.

| Metric | Traditional | FaaS | FaaS/Trad |
|---|---|---|---|
| Wall-clock (s) | 0.145 | 388.99 | 2683× |
| CPU cycles | 316.8 M | 265.2 B | 837× |
| Instructions | 552.9 M | 284.9 B | 515× |
| Context switches | 0 | 52,153 | — |
| Page faults | 3,144 | 4,771,317 | 1518× |

The context-switch and page-fault blowup is the process-spawn cost made visible:
2000 interpreter starts/teardowns versus one long-lived process. Traditional
wins. (Cross-check host: 0.187 s vs 239.56 s, 1281×.)

## (b) Latency under state growth (`bench.state_growth`, sizes 250/500/1000/2000)

FaaS reloads + reserialises the whole (growing) state blob every call → per-call
cost rises, total ~O(N²); Traditional keeps state in memory → ~flat.

| Events | Traditional (s) | FaaS (s) | Ratio | Trad µs/call | FaaS µs/call |
|---|---|---|---|---|---|
| 250 | 0.084 | 39.754 | 471.7× | 337.1 | 159,017 |
| 500 | 0.093 | 77.636 | 830.9× | 186.9 | 155,271 |
| 1000 | 0.103 | 187.652 | 1823.8× | 102.9 | 187,652 |
| 2000 | 0.136 | 371.999 | 2740.0× | 67.9 | 185,999 |

Traditional total stays flat (0.08–0.14 s) and its per-call cost *drops* as fixed
startup amortises (337 → 68 µs); FaaS per-call cost stays ~155–188k µs (dominated
by spawn + growing-blob reload), so the ratio climbs 472× → 2740× across the
range. Traditional wins. (Cross-check host: 204× → 1444×.)

## (c) Parallel throughput on independent CPU — FaaS wins (`bench.parallel_throughput`)

32 independent `project_medals` calls, 3,000,000 iterations each, on 8 vCPUs:

| Architecture | Wall-clock (s) |
|---|---|
| Traditional | 26.914 |
| FaaS | 3.531 |

**Speedup 7.62× → FaaS wins** on the KVM guest; **13.53×** on the bare 8-core
cross-check host (less vCPU scheduling overhead). The monolith is one GIL-bound
process (~1 core); FaaS runs a process per call and uses every core.

## (c2) Spike / load under pressure — FaaS wins (`bench.spike_load`)

The "DoS it and watch it degrade" test. A marquee event ends and spectators slam
the live-standings endpoint (`project_medals`, 200k iters) at once. We ramp
simultaneous clients 8→512, fire a 512-request burst at each level, and record
the latency DISTRIBUTION and sustained throughput (naranja14, 8 vCPU):

| Clients | Trad req/s | Trad p99 (ms) | FaaS req/s | FaaS p99 (ms) |
|---|---|---|---|---|
| 8   | 17.3 | 855   | 89.8 | 99   |
| 32  | 17.4 | 2,283 | 87.5 | 624  |
| 64  | 17.5 | 4,188 | 86.4 | 1,229 |
| 128 | 17.6 | 7,756 | 86.7 | 1,079 |
| 256 | 17.6 | 14,999 | 86.7 | 1,076 |
| 512 | 17.5 | 28,802 | 86.5 | 1,202 |

**At peak (512 clients): FaaS 4.93× the throughput and 23.96× lower p99 latency.**
The monolith's throughput is *pinned at ~17.5 req/s across the entire 8→512 range*
— it never scales — while its p99 tail latency grows linearly with the backlog
(0.9 s → 28.8 s) as every request queues behind one core. FaaS holds ~87 req/s
with bounded tail latency (~1 s): the burst is sprayed across all cores, spawn
cost paid in parallel, not serialized. Neither side refused connections at these
levels (`failed` = 0 throughout); the 256-deep accept backlog absorbed the connects.

**"But the CPU meter showed all cores busy, not one core pinned!"** Measured
directly (`cpu_probe`, 16-client sustained load): the monolith consumes
**1.02 of 8 cores** (13.02 CPU-s over 12.72 s wall). The work is genuinely
~one core's worth; the Linux scheduler just *migrates* the single GIL-holding
thread across all 8 cores, so a per-core meter reads ~13% on each bar instead of
100% on one. The flat 17.5 req/s throughput (would be ~8× higher if truly
multicore) and the 1.02-core aggregate are the ground truth — the even-looking
per-core bars are thread migration, not parallelism.

## (d) Fault isolation — FaaS wins (`bench.fault_isolation`)

One poison `render_highlight(corrupt=True)` call → native crash (`os.abort()`,
SIGABRT, exit -6):

- **Traditional:** the single server process terminated (exit -6); all 5
  in-memory seats lost; subsequent requests refused. Blast radius = whole system.
- **FaaS:** the one subprocess crashed (exit -6), caught by the gateway; 3 more
  bookings after the crash succeeded; `load_state()` showed all 8 seats intact
  (5 pre-crash + 3 post-crash). Blast radius = one request.

## (e) Idle footprint / scale-to-zero — FaaS wins (`bench.idle_footprint`)

- **Traditional:** long-lived process holding **17.4 MB** resident while
  completely idle (0 requests), held continuously.
- **FaaS:** **0 MB, no process** between calls; a call materialises a process
  for ~44 ms, then it is gone.

## (f) Cross-request state leak — FaaS wins by construction (`bench.context_leak`)

40 concurrent bookings, each a **distinct** seat and **distinct** user (no seat
contention — a pure attribution test), race window 0.01 s:

| Architecture | Seats present | Mis-attributed |
|---|---|---|
| Traditional | 40 | **39** |
| FaaS | 40 | **0** |

The monolith's shared `_CTX` global is clobbered across threads, so 39 of 40
seats are recorded against the wrong buyer. FaaS has no shared request context
to leak → 0, by construction.

## (g) Flamegraphs (`results/flamegraphs/`)

CPython's `-X perf` trampoline resolves Python frames, so the cycle-attributed
flamegraphs show *what* each model spends cycles on. Share of CPU cycles (ranges
span both hosts): business-logic ops — Traditional 73–93%, FaaS ≈0%; import +
process spawn + dynamic link — Traditional <1%, FaaS 40–72%; sqlite/external
state — Traditional 0%, FaaS 4–22%. SVGs under `results/flamegraphs/{naranja14,
matanco}/`.

**`perf`-in-a-VM note:** on the KVM guest, `perf stat` counts fine but
`perf record -F 999` captured 0 samples — the slow virtual-PMU overflow interrupt
made the kernel throttle `perf_event_max_sample_rate` toward zero. Fix: fixed
sampling period `perf record -c 2000000` (+ `--call-graph dwarf` since CPython
has no frame pointers; non-precise events only, no guest PEBS).
