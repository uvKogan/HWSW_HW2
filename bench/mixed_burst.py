"""
Mixed, narrative-shaped burst benchmark: realistic multi-op load under stress.

Every existing bench/*.py script isolates one variable (one op, one bug
class) and fires everything at once. This benchmark instead replays
bench/burst_workload.py's timestamped, all-ops timeline against both
architectures through bench/bounded_dispatch.py's paced, concurrency-capped
scheduler -- background Games traffic with a scripted peak (a popular match
goes live, a ticket rush, a CPU-bound medal-projection spike, a shuttle
capacity race) layered on top, instead of a flat replay or an all-at-once
flood.

Two separate, non-conflated results are reported:
  - correctness: does the ticket rush / shuttle-boarding spike produce
    lost updates, with locks/txn off (the default) vs on (--lock/--txn)?
  - phase-scoped latency & throughput: how does each architecture behave
    during each phase, especially the CPU-bound live_medal_projection phase
    -- the one axis this codebase can honestly show a core-parallelism win
    on (both architectures' "safe" mode is a *global* lock/txn, so the
    contended phases are a correctness demonstration, not a throughput one).

Run:
    python -m bench.mixed_burst
    python -m bench.mixed_burst --arch faas --scale 0.1     # quick smoke test
    python -m bench.mixed_burst --lock --txn                # correctness-fixed mode
    python -m bench.mixed_burst --chart-out results/mixed_burst/chart.png
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys

from bench import _serverctl as sc
from bench import bounded_dispatch
from bench import burst_workload
from bench.burst_workload import HOTEL_SHUTTLE_CAPACITY, HOTEL_SHUTTLE_ID

TRADITIONAL_PORT = 8160


# --- Running each architecture -----------------------------------------------


def run_traditional(events: list[dict], pool_size: int, lock: bool) -> tuple[list[dict], int, dict]:
    env = dict(os.environ, OLYMPICS_TICKET_LOCK="1" if lock else "0")
    proc = sc.start_server(TRADITIONAL_PORT, env)
    try:
        def call_fn(op: str, params: dict) -> dict:
            return sc.post_invoke(TRADITIONAL_PORT, op, params)

        records, max_in_flight = bounded_dispatch.run_timeline(
            events, call_fn, pool_size, label="Traditional")
        final_state = sc.post_invoke(TRADITIONAL_PORT, "get_state", {})["state"]
    finally:
        sc.stop_server(proc)
    return records, max_in_flight, final_state


def run_faas(events: list[dict], pool_size: int, txn: bool) -> tuple[list[dict], int, dict]:
    from FaaS import gateway
    from FaaS.storage import load_state, reset_state

    reset_state()
    os.environ["OLYMPICS_FAAS_TXN"] = "1" if txn else "0"

    def call_fn(op: str, params: dict) -> dict:
        return gateway.invoke(op, params)

    records, max_in_flight = bounded_dispatch.run_timeline(
        events, call_fn, pool_size, label="FaaS       ")
    final_state = load_state()
    return records, max_in_flight, final_state


# --- Correctness tallies ------------------------------------------------------


def _seat_rush_tally(records: list[dict]) -> dict:
    sold = collections.Counter()
    attempts = 0
    for r in records:
        if r["phase"] != "ticket_rush_spike":
            continue
        attempts += 1
        if r["result"] and r["result"].get("ok"):
            sold[r["params"]["seat_id"]] += 1
    double_sold = {seat: n for seat, n in sold.items() if n > 1}
    return {"attempts": attempts, "successes": sum(sold.values()),
            "distinct_seats_sold": len(sold), "double_sold": len(double_sold)}


def _hotel_shuttle_tally(records: list[dict], final_state: dict) -> dict:
    attempted_boarding = 0
    for r in records:
        if r["op"] != "dispatch_shuttle" or r["params"].get("shuttle_id") != HOTEL_SHUTTLE_ID:
            continue
        if r["result"] and r["result"].get("ok"):
            attempted_boarding += r["params"].get("seats", 0)
    shuttle = final_state.get("shuttles", {}).get(HOTEL_SHUTTLE_ID, {})
    final_passengers = shuttle.get("passengers", 0)
    capacity = shuttle.get("capacity", HOTEL_SHUTTLE_CAPACITY)
    return {
        "sum_of_successful_boardings": attempted_boarding,
        "final_passengers": final_passengers,
        "capacity": capacity,
        "lost_update": attempted_boarding != final_passengers,
        "overcapacity": final_passengers > capacity,
    }


# --- Phase-scoped latency / throughput ---------------------------------------


def _phase_stats(records: list[dict]) -> dict:
    by_phase: dict = {}
    for r in records:
        by_phase.setdefault(r["phase"], []).append(r)
    stats = {}
    for phase, rs in by_phase.items():
        wall = max(r["end_ts"] for r in rs) - min(r["start_ts"] for r in rs)
        wall = max(wall, 1e-9)
        stats[phase] = {
            "count": len(rs),
            "wall_s": wall,
            "throughput_per_s": len(rs) / wall,
            "errors": sum(1 for r in rs if r["error"]),
        }
    return stats


# --- Reporting ----------------------------------------------------------------


def _print_correctness_table(arch_results: dict) -> None:
    print("\n## Correctness under the ticket rush + hotel-shuttle spike\n")
    print(f"{'architecture':<14} {'seats sold':>10} {'double-sold':>12} "
          f"{'shuttle lost-update':>20} {'shuttle over-capacity':>22}")
    print("-" * 84)
    for arch, (records, _, final_state) in arch_results.items():
        seat = _seat_rush_tally(records)
        hotel = _hotel_shuttle_tally(records, final_state)
        print(f"{arch:<14} {seat['distinct_seats_sold']:>10} {seat['double_sold']:>12} "
              f"{str(hotel['lost_update']):>20} {str(hotel['overcapacity']):>22}")
    print("\n(shuttle capacity race has no artificial widen-the-window hook like "
          "book_ticket's OLYMPICS_RACE_DELAY -- common/operations.py's dispatch_shuttle "
          "wasn't modified to add one, so a lost update there is opportunistic, not "
          "guaranteed every run; the FaaS naive path's larger per-call latency, from real "
          "subprocess+sqlite I/O, makes it the more likely side to reproduce it.)")


def _print_phase_table(arch_results: dict) -> None:
    print("\n## Phase-scoped latency & throughput\n")
    all_phases = list(burst_workload._PHASE_SPEC.keys())
    header = f"{'phase':<24}"
    for arch in arch_results:
        header += f" {arch + ' wall(s)':>16} {arch + ' ops/s':>14}"
    print(header)
    print("-" * len(header))
    for phase in all_phases:
        row = f"{phase:<24}"
        for arch, (records, _, _) in arch_results.items():
            stats = _phase_stats(records).get(phase, {"wall_s": 0.0, "throughput_per_s": 0.0})
            row += f" {stats['wall_s']:>16.3f} {stats['throughput_per_s']:>14.1f}"
        print(row)
    if "Traditional" in arch_results and "FaaS" in arch_results:
        t_stats = _phase_stats(arch_results["Traditional"][0]).get("live_medal_projection")
        f_stats = _phase_stats(arch_results["FaaS"][0]).get("live_medal_projection")
        if t_stats and f_stats and f_stats["wall_s"] > 0:
            speedup = t_stats["wall_s"] / f_stats["wall_s"]
            print(f"\nlive_medal_projection speedup (Traditional/FaaS): {speedup:.2f}x "
                  f"-> {'FaaS' if speedup > 1 else 'Traditional'} wins")


# --- CLI ----------------------------------------------------------------------


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--pool-size", type=int, default=16)
    ap.add_argument("--iterations", type=int, default=2_000_000,
                    help="project_medals iterations per call")
    ap.add_argument("--arch", choices=["traditional", "faas", "both"], default="both")
    ap.add_argument("--lock", action="store_true", help="enable Traditional's global lock")
    ap.add_argument("--txn", action="store_true", help="enable FaaS's transactional_apply")
    ap.add_argument("--race-delay", default="0.01",
                    help="OLYMPICS_RACE_DELAY seconds, widens book_ticket's race window")
    ap.add_argument("--json-out", type=str, help="dump raw per-event records to this JSON path")
    ap.add_argument("--chart-out", type=str, help="write a phase latency/throughput PNG here")
    args = ap.parse_args()

    os.environ["OLYMPICS_RACE_DELAY"] = args.race_delay

    events = burst_workload.generate_timeline(
        seed=args.seed, scale=args.scale, medal_iterations=args.iterations)
    print(f"mixed burst: {len(events)} events, pool size {args.pool_size}, "
          f"arch={args.arch}\n", file=sys.stderr)

    arch_results: dict = {}
    if args.arch in ("traditional", "both"):
        print("== Traditional ==", file=sys.stderr)
        arch_results["Traditional"] = run_traditional(events, args.pool_size, args.lock)
    if args.arch in ("faas", "both"):
        print("== FaaS ==", file=sys.stderr)
        arch_results["FaaS"] = run_faas(events, args.pool_size, args.txn)

    _print_correctness_table(arch_results)
    _print_phase_table(arch_results)

    if args.json_out:
        dump = {arch: records for arch, (records, _, _) in arch_results.items()}
        with open(args.json_out, "w") as f:
            json.dump(dump, f, indent=2)
        print(f"\nwrote per-event records to {args.json_out}")

    if args.chart_out:
        from bench import burst_chart
        burst_chart.render(arch_results, args.chart_out)
        print(f"\nwrote chart to {args.chart_out}")


if __name__ == "__main__":
    main()
