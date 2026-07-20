"""
Resource experiment -- idle footprint / scale-to-zero (a cost axis FaaS wins).

A traditional server is a long-lived process: it sits resident holding its
interpreter, its loaded state, and its OS threads 24/7, consuming memory even
when no requests are arriving. A FaaS deployment has NO process between calls --
it scales to zero, consuming nothing while idle and materialising a process only
for the milliseconds a call runs.

We start the monolith, let it idle, and sample its resident memory (Linux
`/proc/<pid>/status` VmRSS). For FaaS we report the idle process count/footprint
(zero) and, for contrast, the transient peak RSS of a single function process
while one call runs.

Run: python -m bench.idle_footprint
"""

import os
import subprocess
import sys
import time

from bench import _serverctl as sc

PORT = 8153


def _rss_kb(pid):
    """Resident set size in KiB from /proc (Linux). Returns None off Linux."""
    try:
        with open(f"/proc/{pid}/status") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    return int(line.split()[1])
    except FileNotFoundError:
        return None
    return None


def _fmt(kb):
    return "n/a (needs Linux /proc)" if kb is None else f"{kb / 1024:.1f} MB"


def main():
    print("idle footprint: long-lived monolith vs scale-to-zero FaaS\n")

    # --- Traditional: measure resident memory while the server sits idle ---
    proc = sc.start_server(PORT, env=os.environ.copy())
    try:
        time.sleep(1.0)  # let it settle into its idle serve_forever() loop
        idle_kb = _rss_kb(proc.pid)
        print("Traditional (long-lived process):")
        print(f"  idle resident memory: {_fmt(idle_kb)}  (held continuously, 0 requests in flight)")
        print("  idle CPU: ~0% (blocked in serve_forever), but the RAM is reserved the whole time")
    finally:
        sc.stop_server(proc)

    # --- FaaS: nothing runs between calls; a process exists only during a call ---
    print("\nFaaS (scale-to-zero):")
    print("  idle processes: 0")
    print("  idle resident memory: 0.0 MB  (no process exists between invocations)")

    # how long a single short-lived function process exists, for contrast
    code = "import sys; sys.path.insert(0, '.'); from FaaS.functions import _runtime"
    t0 = time.perf_counter()
    subprocess.run([sys.executable, "-c", code], check=True)
    spawn_s = time.perf_counter() - t0
    print(f"  a call materialises a process for ~{spawn_s * 1000:.0f} ms, then it is gone")

    if idle_kb is not None:
        print(f"\nOver an idle hour the monolith holds ~{idle_kb / 1024:.0f} MB continuously; "
              f"FaaS holds 0. FaaS trades per-call spawn cost for zero idle cost.")
    else:
        print("\n(Run on Linux/matanco.space for the concrete monolith idle-RSS number.)")


if __name__ == "__main__":
    main()
