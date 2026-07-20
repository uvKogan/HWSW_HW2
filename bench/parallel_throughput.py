"""
Concurrency experiment #2 -- parallel throughput on independent CPU work
(the axis FaaS wins).

Fire M independent, CPU-bound `project_medals` calls concurrently at each
architecture and measure wall-clock:

  Traditional: the ThreadingHTTPServer runs each request in a thread, but the
    work is pure-Python CPU, so the GIL serialises it -> ~one core -> total
    time grows ~linearly with M.
  FaaS: each call is its own process (project_medals is compute-only, no
    state I/O), so the OS spreads them across cores -> total time ~ M/cores
    (plus per-call spawn cost).

On a multicore box FaaS should win once per-call compute outweighs spawn
overhead (tune --iterations). Best run on Linux (real fork + many cores);
on Windows the heavier `spawn` inflates the FaaS side.

Run: python -m bench.parallel_throughput --tasks 16 --iterations 3000000
"""

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor

from bench import _serverctl as sc
from FaaS import gateway
from common import reference_data as ref

PORT = 8138


def _tasks(m: int, iterations: int):
    codes = [c["code"] for c in ref.COUNTRIES]
    return [{"country_code": codes[i % len(codes)], "iterations": iterations} for i in range(m)]


def run_traditional(tasks) -> float:
    env = dict(os.environ)
    proc = sc.start_server(PORT, env)
    try:
        t0 = time.perf_counter()
        with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
            list(ex.map(lambda t: sc.post_invoke(PORT, "project_medals", t), tasks))
        return time.perf_counter() - t0
    finally:
        sc.stop_server(proc)


def run_faas(tasks) -> float:
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        list(ex.map(lambda t: gateway.invoke("project_medals", t), tasks))
    return time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", type=int, default=32)
    ap.add_argument("--iterations", type=int, default=5_000_000)
    args = ap.parse_args()

    tasks = _tasks(args.tasks, args.iterations)
    cores = os.cpu_count()
    print(f"parallel throughput: {args.tasks} independent project_medals calls "
          f"@ {args.iterations:,} iters each, on {cores} cores\n")

    trad = run_traditional(tasks)
    faas = run_faas(tasks)

    print(f"{'architecture':<16} {'wall-clock (s)':>16}")
    print("-" * 34)
    print(f"{'Traditional':<16} {trad:>16.3f}")
    print(f"{'FaaS':<16} {faas:>16.3f}")
    winner = "FaaS" if faas < trad else "Traditional"
    print(f"\nspeedup (Traditional/FaaS): {trad / faas:.2f}x  -> {winner} wins")


if __name__ == "__main__":
    main()
