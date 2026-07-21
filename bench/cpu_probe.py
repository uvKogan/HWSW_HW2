"""
Diagnostic: how many CPU cores does the naive monolith actually use under load?

Motivation: while the spike test runs, a per-core CPU meter shows load spread
*evenly* across all cores rather than one core pegged at 100% -- which looks like
the monolith is parallel. It is not. The single GIL-holding thread is simply
migrated across cores by the scheduler, so each core shows a fraction of the load
that sums to ~one core. This probe proves it by measuring the server process's
AGGREGATE CPU time (utime+stime over all its threads, from /proc/<pid>/stat) over
a fixed wall-clock window of sustained load, and dividing to get cores-used.

Expected: ~1.0 cores of 8 (GIL ceiling), matching the flat throughput in
bench.spike_load. Linux only (reads /proc). Run: python -m bench.cpu_probe
"""

import os
import time
from concurrent.futures import ThreadPoolExecutor

from bench import _serverctl as sc

PORT = 8177
CLK = os.sysconf("SC_CLK_TCK")
CODES = ["USA", "CHN", "GBR", "GER", "FRA", "JPN", "AUS", "ITA"]


def _proc_cpu_ticks(pid):
    """utime+stime for the whole process (all threads) from /proc/<pid>/stat."""
    with open(f"/proc/{pid}/stat") as f:
        parts = f.read().split()
    return int(parts[13]) + int(parts[14])  # fields 14,15 (0-indexed 13,14)


def main(clients=16, seconds=12, iterations=200_000):
    proc = sc.start_server(PORT, dict(os.environ))
    pid = proc.pid
    deadline = time.time() + seconds

    def hammer(i):
        while time.time() < deadline:
            sc.post_invoke(PORT, "project_medals",
                           {"country_code": CODES[i % len(CODES)], "iterations": iterations})

    try:
        sc.post_invoke(PORT, "project_medals", {"country_code": "USA", "iterations": 1000})  # warm up
        t0, c0 = time.perf_counter(), _proc_cpu_ticks(pid)
        with ThreadPoolExecutor(max_workers=clients) as ex:
            list(ex.map(hammer, range(clients)))
        wall, cpu_s = time.perf_counter() - t0, (_proc_cpu_ticks(pid) - c0) / CLK
        cores = cpu_s / wall
        print(f"monolith under {clients}-client load: wall={wall:.2f}s  "
              f"cpu_time={cpu_s:.2f}s  => {cores:.2f} cores used (of {os.cpu_count()})")
        print("~1 core confirms the GIL ceiling; the 'even across cores' meter is "
              "scheduler migration of one thread, not parallelism.")
    finally:
        sc.stop_server(proc)


if __name__ == "__main__":
    main()
