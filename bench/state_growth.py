"""
Part 4 experiment -- latency under state growth.

Replays the same deterministic workload at increasing event counts and times
each architecture. The FaaS runtime reloads and reserialises the ENTIRE state
blob (which grows with every event -- especially the append-only log) on every
single call, so its per-call cost climbs as the run progresses: total work is
roughly O(N^2). The Traditional monolith keeps state in memory and appends in
O(1), so it stays ~linear. Watch the ratio grow with N.

Run: python -m bench.state_growth
"""

import argparse
import subprocess
import sys
import time
from pathlib import Path


def _time(cmd) -> float:
    t0 = time.perf_counter()
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL)
    return time.perf_counter() - t0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[500, 1000, 2000, 5000])
    args = ap.parse_args()

    print(f"{'events':>7} {'Traditional(s)':>15} {'FaaS(s)':>10} {'ratio':>8} "
          f"{'Trad us/call':>13} {'FaaS us/call':>13}")
    print("-" * 70)
    for n in args.sizes:
        wl = Path(f"wl_{n}.json")
        subprocess.run([sys.executable, "-m", "common.workload", "42", str(n), str(wl)],
                       check=True, stdout=subprocess.DEVNULL)
        t_trad = _time([sys.executable, "-m", "Traditional.server", "--workload", str(wl)])
        subprocess.run([sys.executable, "-c", "from FaaS.storage import reset_state; reset_state()"],
                       check=True)
        t_faas = _time([sys.executable, "-m", "FaaS.gateway", "--workload", str(wl)])
        wl.unlink(missing_ok=True)
        print(f"{n:>7} {t_trad:>15.3f} {t_faas:>10.3f} {t_faas / t_trad:>7.1f}x "
              f"{t_trad / n * 1e6:>12.1f} {t_faas / n * 1e6:>12.1f}")


if __name__ == "__main__":
    main()
