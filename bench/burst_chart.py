"""
Optional matplotlib chart for bench/mixed_burst.py's phase-scoped results.

Imported lazily (only when --chart-out is passed) so the rest of the
benchmark stays runnable without matplotlib installed -- every other
bench/*.py script in this repo is stdlib-only by design (see script.sh's
header comment), and this is the one deliberate, isolated exception, scoped
to a single optional output format.
"""

from __future__ import annotations

import os


def render(arch_results: dict, out_path: str) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("WARNING: matplotlib not available -- skipping --chart-out "
              f"({out_path} not written)")
        return

    from bench.mixed_burst import _phase_stats

    phases = ["background_trickle", "hotel_shuttle_prefill", "streaming_peak",
              "hotel_shuttle_spike", "ticket_rush_spike", "live_medal_projection",
              "wind_down"]
    archs = list(arch_results.keys())
    colors = {"Traditional": "#4C72B0", "FaaS": "#DD8452"}

    fig, (ax_wall, ax_throughput) = plt.subplots(1, 2, figsize=(13, 5))
    width = 0.35
    x = range(len(phases))

    for i, arch in enumerate(archs):
        records = arch_results[arch][0]
        stats = _phase_stats(records)
        walls = [stats.get(p, {"wall_s": 0.0})["wall_s"] for p in phases]
        throughputs = [stats.get(p, {"throughput_per_s": 0.0})["throughput_per_s"] for p in phases]
        offset = (i - (len(archs) - 1) / 2) * width
        color = colors.get(arch, None)
        ax_wall.bar([xi + offset for xi in x], walls, width, label=arch, color=color)
        ax_throughput.bar([xi + offset for xi in x], throughputs, width, label=arch, color=color)

    for ax, title, ylabel in (
        (ax_wall, "Phase wall-clock", "seconds"),
        (ax_throughput, "Phase throughput", "ops/sec"),
    ):
        ax.set_xticks(list(x))
        ax.set_xticklabels(phases, rotation=30, ha="right", fontsize=8)
        ax.set_title(title)
        ax.set_ylabel(ylabel)
        ax.legend()
        ax.grid(axis="y", alpha=0.3)

    # Highlight the phase this benchmark is honestly built to demonstrate a
    # FaaS win on (see bench/mixed_burst.py's module docstring).
    if "live_medal_projection" in phases:
        idx = phases.index("live_medal_projection")
        for ax in (ax_wall, ax_throughput):
            ax.axvspan(idx - 0.5, idx + 0.5, color="gold", alpha=0.15, zorder=0)

    fig.suptitle("Mixed-burst benchmark: phase-scoped latency & throughput\n"
                 "(gold band = the CPU-bound axis this benchmark honestly shows FaaS winning on)")
    fig.tight_layout()

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
