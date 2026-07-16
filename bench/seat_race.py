"""
Concurrency experiment #1 -- seat-booking race (the axis Traditional wins).

Many simulated users concurrently try to buy the SAME seats. Correct
behaviour: exactly one buyer succeeds per seat. A double-sold seat (two
`ok: True` responses for one seat) proves a lost update from an unguarded
check-then-write.

We run four scenarios, all with OLYMPICS_RACE_DELAY set so the race window is
observable:

  Traditional, no lock   -> unguarded threads sharing STATE: races
  Traditional, +lock     -> OLYMPICS_TICKET_LOCK=1: one in-process lock fixes it
  FaaS, no transaction   -> independent processes, separate load/save: races hard
  FaaS, +transaction     -> OLYMPICS_FAAS_TXN=1: BEGIN IMMEDIATE serialises it

Double-sells are detected purely from responses (count of ok:True per seat),
so no state-inspection endpoint is needed.

Run: python -m bench.seat_race
"""

import argparse
import collections
import os
from concurrent.futures import ThreadPoolExecutor

from bench import _serverctl as sc
from FaaS import gateway
from FaaS.storage import reset_state

PORT = 8137
MATCH = "match_final"


def _tasks(n_users: int, n_seats: int):
    """User i contends for seat (i % n_seats), so ~n_users/n_seats buyers race
    for each seat."""
    return [
        {"match_id": MATCH, "seat_id": f"seat{i % n_seats}", "user_id": f"user{i:03d}"}
        for i in range(n_users)
    ]


def _tally(results, n_seats: int) -> dict:
    sold = collections.Counter()
    for r in results:
        if r.get("ok"):
            sold[r["seat_id"]] += 1
    double = {seat: c for seat, c in sold.items() if c > 1}
    return {
        "successes": sum(sold.values()),
        "distinct_seats_sold": len(sold),
        "double_sold": double,
    }


def run_traditional(tasks, n_seats, lock: bool, delay: str) -> dict:
    env = dict(os.environ, OLYMPICS_RACE_DELAY=delay,
               OLYMPICS_TICKET_LOCK="1" if lock else "0")
    proc = sc.start_server(PORT, env)
    try:
        with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
            results = list(ex.map(
                lambda t: {**sc.post_invoke(PORT, "book_ticket", t), "seat_id": t["seat_id"]},
                tasks,
            ))
    finally:
        sc.stop_server(proc)
    return _tally(results, n_seats)


def run_faas(tasks, n_seats, txn: bool, delay: str) -> dict:
    reset_state()
    os.environ["OLYMPICS_RACE_DELAY"] = delay
    os.environ["OLYMPICS_FAAS_TXN"] = "1" if txn else "0"
    with ThreadPoolExecutor(max_workers=len(tasks)) as ex:
        results = list(ex.map(
            lambda t: {**gateway.invoke("book_ticket", t), "seat_id": t["seat_id"]},
            tasks,
        ))
    return _tally(results, n_seats)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--users", type=int, default=30)
    ap.add_argument("--seats", type=int, default=10)
    ap.add_argument("--delay", default="0.02", help="race-window seconds (env OLYMPICS_RACE_DELAY)")
    args = ap.parse_args()

    tasks = _tasks(args.users, args.seats)
    print(f"seat-race: {args.users} users contend for {args.seats} seats "
          f"(~{args.users / args.seats:.0f} buyers/seat), race window {args.delay}s\n")

    scenarios = [
        ("Traditional  no-lock ", lambda: run_traditional(tasks, args.seats, False, args.delay)),
        ("Traditional  +lock   ", lambda: run_traditional(tasks, args.seats, True, args.delay)),
        ("FaaS         no-txn  ", lambda: run_faas(tasks, args.seats, False, args.delay)),
        ("FaaS         +txn    ", lambda: run_faas(tasks, args.seats, True, args.delay)),
    ]

    print(f"{'scenario':<22} {'ok':>4} {'seats':>6} {'double-sold':>12}")
    print("-" * 48)
    for name, fn in scenarios:
        t = fn()
        n_double = len(t["double_sold"])
        flag = "  <-- BUG" if n_double else ""
        print(f"{name:<22} {t['successes']:>4} {t['distinct_seats_sold']:>6} {n_double:>12}{flag}")

    print(f"\n(expected correct result: ok={args.seats}, seats={args.seats}, double-sold=0)")


if __name__ == "__main__":
    main()
