# Part 4 — Measured Results

All numbers measured on the `matanco.space` box: **8-core x86_64 Linux**
(kernel 7.1.0-rc1), **Python 3.12.3**, **perf/linux-tools 6.8**. Reproduce with
`./script.sh` or the individual `python3 -m bench.*` commands.

The comparison is balanced but FaaS-favored: Traditional wins the two
sequential/stateful axes (a, b); FaaS wins the four isolation/elasticity/
correctness axes (c, d, e, f).

## (a) Per-call overhead — base 2000-event workload (`perf stat`)

`perf stat` follows forked children, so FaaS aggregates all 2000 spawned processes.

| Metric | Traditional | FaaS | FaaS/Trad |
|---|---|---|---|
| Wall-clock (s) | 0.187 | 239.56 | 1281× |
| Task-clock (ms) | 171.27 | 220,886 | 1290× |
| CPU cycles | 459.6 M | 487.3 B | 1060× |
| Instructions | 775.6 M | 767.3 B | 989× |
| Context switches | 1 | 19,983 | 19,983× |
| Page faults | 3,203 | 4,302,009 | 1343× |

The ~20,000× context-switch and 1343× page-fault blowup is the process-spawn
cost made visible: 2000 interpreter starts/teardowns versus one long-lived
process. Traditional wins.

## (b) Latency under state growth (`bench.state_growth`, sizes 250/500/1000/2000)

FaaS reloads + reserialises the whole (growing) state blob every call → per-call
cost rises, total ~O(N²); Traditional keeps state in memory → ~flat.

| Events | Traditional (s) | FaaS (s) | Ratio | Trad µs/call | FaaS µs/call |
|---|---|---|---|---|---|
| 250 | 0.118 | 23.945 | 203.5× | 470.6 | 95,779.8 |
| 500 | 0.140 | 48.911 | 348.6× | 280.6 | 97,821.9 |
| 1000 | 0.125 | 100.921 | 809.2× | 124.7 | 100,921.4 |
| 2000 | 0.145 | 209.134 | 1444.3× | 72.4 | 104,567.2 |

Traditional total stays flat (0.12–0.15 s) and its per-call cost *drops* as
fixed startup amortises; FaaS per-call cost *rises* (95.8k → 104.6k µs) as the
reloaded blob grows, so the ratio climbs 204× → 1444× across the range.
Traditional wins.

## (c) Parallel throughput on independent CPU — FaaS wins (`bench.parallel_throughput`)

32 independent `project_medals` calls, 3,000,000 iterations each, on 8 cores:

| Architecture | Wall-clock (s) |
|---|---|
| Traditional | 36.509 |
| FaaS | 2.698 |

**Speedup 13.53× → FaaS wins.** The monolith is one GIL-bound process (~1 core);
FaaS runs a process per call and uses all 8 cores.

## (d) Fault isolation — FaaS wins (`bench.fault_isolation`)

One poison `render_highlight(corrupt=True)` call → native crash (`os.abort()`,
SIGABRT, exit -6):

- **Traditional:** the single server process terminated (exit -6); all 5
  in-memory seats lost; subsequent requests refused. Blast radius = whole system.
- **FaaS:** the one subprocess crashed (exit -6), caught by the gateway; 3 more
  bookings after the crash succeeded; `load_state()` showed all 8 seats intact
  (5 pre-crash + 3 post-crash). Blast radius = one request.

## (e) Idle footprint / scale-to-zero — FaaS wins (`bench.idle_footprint`)

- **Traditional:** long-lived process holding **20.1 MB** resident while
  completely idle (0 requests), held continuously.
- **FaaS:** **0 MB, no process** between calls; a call materialises a process
  for ~100 ms, then it is gone.

## (f) Cross-request state leak — FaaS wins by construction (`bench.context_leak`)

40 concurrent bookings, each a **distinct** seat and **distinct** user (no seat
contention — a pure attribution test), race window 0.01 s:

| Architecture | Seats present | Mis-attributed |
|---|---|---|
| Traditional | 40 | **34** |
| FaaS | 40 | **0** |

The monolith's shared `_CTX` global is clobbered across threads, so 34 of 40
seats are recorded against the wrong buyer. FaaS has no shared request context
to leak → 0, by construction.
