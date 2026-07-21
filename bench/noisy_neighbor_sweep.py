"""
Noisy-neighbor scaling sweep: how does a heavy CPU caller's per-call cost degrade
*unrelated* concurrent work, and does that degradation scale differently on the
two architectures?

This drives bench/mixed_burst.py's timeline at a range of medal-projection
iteration counts and, for each, records two phase-wall numbers per architecture:
the CPU-bound `live_medal_projection` phase (the heavy caller) and the
`background_trickle` phase (unrelated light work that runs the whole time). The
finding (see report §4h): on the monolith, background work is flat until the
medal phase outgrows its time window, then climbs *linearly* with the heavy load
(GIL monopolization starves everything sharing the process); on FaaS it stays
flat, because each call is its own process. The two cross once the monolith's
starvation tax exceeds FaaS's fixed per-call overhead.

Optional matplotlib chart (lazily imported, like bench/burst_chart.py) draws the
two panels used in the report. Linux-friendly; each point runs both architectures
once, so a full sweep with heavy top-end iterations takes a few minutes.

Run:
    python -m bench.noisy_neighbor_sweep \
        --iters 25000,50000,75000,100000,125000,250000,500000,1000000,2000000 \
        --json-out results/mixed_burst/sweep_summary.json \
        --chart-out results/mixed_burst/sweep_noisy_neighbor.png
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from bench import burst_workload
from bench import mixed_burst as mb


def run_point(iters: int, scale: float, pool_size: int) -> dict:
    """Run the mixed-burst timeline once per architecture at `iters` medal
    iterations; return the two phase-wall numbers per architecture."""
    events = burst_workload.generate_timeline(seed=42, scale=scale, medal_iterations=iters)
    t_records, _, _ = mb.run_traditional(events, pool_size, lock=False)
    f_records, _, _ = mb.run_faas(events, pool_size, txn=False)
    ts, fs = mb._phase_stats(t_records), mb._phase_stats(f_records)

    def wall(stats, phase):
        return stats.get(phase, {"wall_s": 0.0})["wall_s"]

    row = {
        "iters": iters,
        "trad_medal_s": wall(ts, "live_medal_projection"),
        "faas_medal_s": wall(fs, "live_medal_projection"),
        "trad_bg_s": wall(ts, "background_trickle"),
        "faas_bg_s": wall(fs, "background_trickle"),
    }
    row["medal_speedup"] = row["trad_medal_s"] / row["faas_medal_s"] if row["faas_medal_s"] else 0.0
    return row


def render_chart(points: list[dict], out_path: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"WARNING: matplotlib not available -- skipping chart ({out_path})")
        return

    xs = [p["iters"] / 1e6 for p in points]
    C = {"Traditional": "#4C72B0", "FaaS": "#DD8452"}
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4.6))

    ax1.plot(xs, [p["trad_medal_s"] for p in points], "o-", color=C["Traditional"], label="Traditional")
    ax1.plot(xs, [p["faas_medal_s"] for p in points], "o-", color=C["FaaS"], label="FaaS")
    ax1.set_title("CPU-bound medal phase: wall-clock vs per-call load")
    ax1.set_xlabel("medal iterations per call (millions)")
    ax1.set_ylabel("phase wall-clock (s)")
    ax1.legend(); ax1.grid(alpha=0.3)

    ax2.plot(xs, [p["trad_bg_s"] for p in points], "o-", color=C["Traditional"], label="Traditional")
    ax2.plot(xs, [p["faas_bg_s"] for p in points], "o-", color=C["FaaS"], label="FaaS")
    ax2.set_title("Unrelated background work: completion time vs heavy-caller load")
    ax2.set_xlabel("medal iterations per call (millions)")
    ax2.set_ylabel("background-phase completion (s)")
    ax2.legend(); ax2.grid(alpha=0.3)

    fig.suptitle("Non-linearity of GIL starvation: heavier CPU callers disproportionately "
                 "degrade unrelated work in the monolith, not in FaaS")
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--iters", type=str,
                    default="25000,50000,75000,100000,125000,250000,500000,1000000,2000000",
                    help="comma-separated medal iteration counts to sweep")
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--pool-size", type=int, default=16)
    ap.add_argument("--race-delay", default="0.01")
    ap.add_argument("--json-out", type=str, help="dump the per-point summary here")
    ap.add_argument("--chart-out", type=str, help="write the two-panel PNG here")
    args = ap.parse_args()

    os.environ["OLYMPICS_RACE_DELAY"] = args.race_delay
    iters_list = [int(x) for x in args.iters.split(",") if x.strip()]

    points = []
    for i, iters in enumerate(iters_list, 1):
        print(f"[{i}/{len(iters_list)}] iters={iters:,} ...", file=sys.stderr)
        row = run_point(iters, args.scale, args.pool_size)
        points.append(row)
        print(f"    medal: Trad {row['trad_medal_s']:.1f}s vs FaaS {row['faas_medal_s']:.1f}s "
              f"({row['medal_speedup']:.1f}x)   background: Trad {row['trad_bg_s']:.1f}s "
              f"vs FaaS {row['faas_bg_s']:.1f}s", file=sys.stderr)

    print(f"\n{'iters':>10} {'medalTrad':>10} {'medalFaaS':>10} {'speedup':>8} "
          f"{'bgTrad':>8} {'bgFaaS':>8}")
    for p in points:
        print(f"{p['iters']:>10} {p['trad_medal_s']:>10.1f} {p['faas_medal_s']:>10.1f} "
              f"{p['medal_speedup']:>7.1f}x {p['trad_bg_s']:>8.1f} {p['faas_bg_s']:>8.1f}")

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(points, f, indent=2)
        print(f"\nwrote summary to {args.json_out}")
    if args.chart_out:
        render_chart(points, args.chart_out)
        print(f"wrote chart to {args.chart_out}")


if __name__ == "__main__":
    main()
