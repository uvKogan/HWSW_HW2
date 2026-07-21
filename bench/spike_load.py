"""
Spike / load-under-pressure experiment -- latency and throughput as concurrency
ramps (the "DoS it and watch it degrade" test; the axis FaaS wins under load).

Real Games scenario: a marquee medal event finishes and thousands of spectators
refresh the live standings at the same instant -- a burst of read-heavy CPU work
(`project_medals`, the same embarrassingly-parallel op as bench.parallel_throughput,
but here we care about how the system BEHAVES under a spike, not just total time).

At each concurrency level we fire a fixed burst of requests through a pool of that
many simultaneous clients and record, per request, its end-to-end latency and
whether it succeeded. From that we report the numbers a single wall-clock can't
show: sustained throughput (req/s) and the LATENCY DISTRIBUTION (p50/p95/p99/max),
plus any refused / errored requests.

  Traditional (naive monolith): one long-lived, GIL-bound process. Its threads
    accept every connection, but the pure-Python CPU work serialises on ~one
    core, so throughput plateaus no matter how many clients pile on and the
    request backlog grows -> p95/p99 tail latency explodes as the spike
    intensifies; past the 256-deep accept backlog, connects are refused.
  FaaS: each call is its own process, so the OS sprays the burst across every
    core -> throughput scales with cores and tail latency stays bounded (the
    per-call spawn cost is paid in parallel, not queued behind one core).

At high concurrency this is a literal denial-of-service test: once simultaneous
clients exceed the monolith's 256-deep accept backlog, connects are REFUSED
(the failed column climbs) -- a single process has a hard ceiling. FaaS has no
shared accept queue to overflow.

Run: python -m bench.spike_load --levels 8,32,64,128,256,512 --burst 512 --iterations 200000
"""

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from bench import _serverctl as sc
from FaaS import gateway
from common import reference_data as ref

PORT = 8162
CODES = [c["code"] for c in ref.COUNTRIES]


def _percentile(xs, p):
    """Linear-interpolated pth percentile of `xs` (already-collected latencies)."""
    if not xs:
        return float("nan")
    s = sorted(xs)
    if len(s) == 1:
        return s[0]
    k = (len(s) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def _trad_call(i, iterations):
    code = CODES[i % len(CODES)]
    t0 = time.perf_counter()
    try:
        sc.post_invoke(PORT, "project_medals", {"country_code": code, "iterations": iterations})
        return time.perf_counter() - t0, True
    except Exception:
        return time.perf_counter() - t0, False


def _faas_call(i, iterations):
    code = CODES[i % len(CODES)]
    t0 = time.perf_counter()
    try:
        gateway.invoke("project_medals", {"country_code": code, "iterations": iterations})
        return time.perf_counter() - t0, True
    except Exception:
        return time.perf_counter() - t0, False


def _run_burst(call, iterations, burst, level):
    """Fire `burst` requests through `level` simultaneous clients; return
    (wall_seconds, latencies, n_ok)."""
    lat = []
    ok = 0
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=level) as ex:
        futs = [ex.submit(call, i, iterations) for i in range(burst)]
        for fu in as_completed(futs):
            latency, good = fu.result()
            lat.append(latency)
            ok += 1 if good else 0
    return time.perf_counter() - t0, lat, ok


def _sweep(name, call, iterations, burst, levels):
    print(f"\n=== {name} ===")
    print(f"{'clients':>8} {'req/s':>10} {'p50 ms':>9} {'p95 ms':>9} "
          f"{'p99 ms':>9} {'max ms':>9} {'failed':>8}")
    print("-" * 66)
    rows = []
    for level in levels:
        wall, lat, ok = _run_burst(call, iterations, burst, level)
        failed = burst - ok
        thru = ok / wall if wall > 0 else 0.0
        row = {
            "clients": level,
            "req_s": thru,
            "p50": _percentile(lat, 50) * 1000,
            "p95": _percentile(lat, 95) * 1000,
            "p99": _percentile(lat, 99) * 1000,
            "max": max(lat) * 1000 if lat else float("nan"),
            "failed": failed,
        }
        rows.append(row)
        print(f"{level:>8} {thru:>10.1f} {row['p50']:>9.1f} {row['p95']:>9.1f} "
              f"{row['p99']:>9.1f} {row['max']:>9.1f} {failed:>8}")
    return rows


def run_traditional(iterations, burst, levels):
    proc = sc.start_server(PORT, dict(os.environ))
    try:
        return _sweep("Traditional (naive monolith)", _trad_call, iterations, burst, levels)
    finally:
        sc.stop_server(proc)


def run_faas(iterations, burst, levels):
    return _sweep("FaaS (process-per-call)", _faas_call, iterations, burst, levels)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--levels", type=str, default="8,32,64,128,256,512",
                    help="comma-separated concurrency levels (simultaneous clients)")
    ap.add_argument("--burst", type=int, default=512,
                    help="requests fired at each concurrency level")
    ap.add_argument("--iterations", type=int, default=200_000,
                    help="per-call project_medals iterations (CPU cost)")
    args = ap.parse_args()
    levels = [int(x) for x in args.levels.split(",") if x.strip()]
    cores = os.cpu_count()

    print(f"spike load: burst of {args.burst} project_medals requests "
          f"@ {args.iterations:,} iters each, ramping clients {levels}, on {cores} cores")

    trad = run_traditional(args.iterations, args.burst, levels)
    faas = run_faas(args.iterations, args.burst, levels)

    # Headline comparison at peak concurrency.
    peak_t, peak_f = trad[-1], faas[-1]

    def _ratio(a, b):
        return f"{a / b:.2f}x" if b else "n/a (div0)"

    print(f"\n--- at peak ({levels[-1]} concurrent clients) ---")
    print(f"throughput:  Traditional {peak_t['req_s']:.1f} req/s   "
          f"FaaS {peak_f['req_s']:.1f} req/s   "
          f"({_ratio(peak_f['req_s'], peak_t['req_s'])} FaaS)")
    print(f"p99 latency: Traditional {peak_t['p99']:.0f} ms   "
          f"FaaS {peak_f['p99']:.0f} ms   "
          f"({_ratio(peak_t['p99'], peak_f['p99'])} lower for FaaS)")
    if peak_t["failed"] or peak_f["failed"]:
        print(f"refused:     Traditional {peak_t['failed']}   FaaS {peak_f['failed']}")


if __name__ == "__main__":
    main()
