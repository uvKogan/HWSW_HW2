# Part 4 — Measured Results

All measurements on **matanco.space**: 8-core Linux (kernel 7.1.0-rc1),
Python 3.12.3, `perf` (linux-tools 6.8). Reproduce with `./script.sh` plus
`python3 -m bench.state_growth`. `perf stat` follows forked children, so the
FaaS figures aggregate all spawned function processes.

## 1. `perf stat` — base workload (200 events, one replay)

| Metric | Traditional | FaaS | FaaS / Traditional |
|---|---:|---:|---:|
| Wall-clock (s) | 0.125 | 19.236 | 154× |
| task-clock (ms) | 108.96 | 16,162.4 | 148× |
| CPU cycles | 342.7 M | 47.20 B | 138× |
| Instructions | 490.8 M | 64.78 B | 132× |
| Context switches | 5 | 3,154 | 631× |
| Page faults | 2,612 | 321,810 | 123× |
| CPU migrations | 0 | 207 | — |

Cause: FaaS spawns a fresh interpreter **per call** (200 processes) and does a
sqlite load+save each time; Traditional runs the same 200 ops in one process
against in-memory state. The context-switch and page-fault blowup is the
process-spawn cost made visible.

## 2. State-growth scaling (per-call cost as state grows)

| Events | Traditional (s) | FaaS (s) | Ratio | Trad µs/call | FaaS µs/call |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.134 | 8.696 | 65× | 1339.5 | 86,958 |
| 500 | 0.153 | 44.640 | 291× | 306.4 | 89,280 |
| 1000 | 0.128 | 92.156 | 718× | 128.4 | 92,156 |
| 2000 | 0.169 | 212.637 | 1258× | 84.5 | 106,319 |

Traditional total stays ~flat (work is trivial in memory; per-call cost falls
as fixed startup amortises). FaaS grows super-linearly: each call reloads and
reserialises the whole state blob — which grows with every event, especially
the append-only log — so per-call cost rises (87 → 106 µs... ms) and the ratio
climbs from 65× to 1258×. Total FaaS work ≈ O(N²) vs. Traditional O(N).

## 3. Parallel throughput — independent CPU work (the FaaS win)

16 independent `project_medals` calls @ 3,000,000 iterations each, 8 cores:

| Architecture | Wall-clock (s) |
|---|---:|
| Traditional (threaded server, GIL-bound) | 12.445 |
| FaaS (process per call, multicore) | 2.125 |

**FaaS wins 5.86×.** The monolith is one Python process, so the GIL serialises
CPU-bound work onto ~one core; FaaS runs each call in its own process, so the 8
cores are actually used. This is the mirror image of §4 — same concurrency
theme, opposite winner.

## 4. Seat-booking race — shared contended state (the Traditional win)

30 users contend for 10 seats (~3 buyers/seat), 0.02 s race window:

| Scenario | ok | seats | double-sold |
|---|---:|---:|---:|
| Traditional, no lock | 15 | 10 | 4 (BUG) |
| Traditional, +lock | 10 | 10 | 0 |
| FaaS, no transaction | 24 | 10 | 8 (BUG) |
| FaaS, +transaction | 10 | 10 | 0 |

Both architectures oversell without protection (FaaS worse — the race spans
whole processes). The fixes differ in weight: Traditional needs **one
in-process `threading.Lock`**; FaaS needs a **`BEGIN IMMEDIATE` transaction**
spanning load→op→save, and because state is a single JSON blob that lock is
effectively *global*, not per-seat — the coarse-external-state tax.
