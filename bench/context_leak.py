"""
Correctness experiment -- cross-request state leakage (the axis FaaS wins by
construction).

The naive monolith stashes "the current request's actor" in a *module global*
(`_CTX` in Traditional/server.py) and later reads it back when recording who
bought a seat. Single-threaded that is fine. But the server is a
ThreadingHTTPServer, so two overlapping `book_ticket` requests clobber the
shared `_CTX`: request A can end up recording *B's* user id against A's seat.
That is a silent data-integrity / attribution bug -- the seat is sold to the
wrong person -- and it is exactly the class of bug a long-lived shared-memory
process invites.

We fire N concurrent bookings, each for a DISTINCT seat and a DISTINCT user
(so there is no seat contention to confuse things -- purely an attribution
test), then read the state back and count seats recorded against the wrong
buyer.

  Traditional (naive monolith): shared `_CTX` -> many mis-attributed seats.
  FaaS: each call is its own process with no shared memory, so there is no
    request-context global to leak. Zero mis-attributions, by construction.

For FaaS we enable its serialization fix (OLYMPICS_FAAS_TXN) so lost-updates --
the orthogonal issue already covered by bench/seat_race.py -- don't muddy the
attribution measurement. (Note: a coarse lock would also mask the monolith's
leak; the deeper point is that FaaS *cannot have* this bug, it has no shared
request context to corrupt.)

Run: python -m bench.context_leak --seats 40 --delay 0.01
"""

import argparse
import os
from concurrent.futures import ThreadPoolExecutor

from bench import _serverctl as sc

PORT = 8151
MATCH = "leak_match"


def _bookings(n):
    # task i books seat{i} for user{i:03d}; expected owner of seat{i} is user{i:03d}
    return [(f"seat{i}", f"user{i:03d}") for i in range(n)]


def _fire(fn, bookings):
    with ThreadPoolExecutor(max_workers=len(bookings)) as ex:
        list(ex.map(fn, bookings))


def _misattributed(seats, bookings):
    present = 0
    wrong = 0
    for seat_id, user_id in bookings:
        owner = seats.get(seat_id)
        if owner is None:
            continue  # not present (a lost update -- orthogonal, not attribution)
        present += 1
        if owner != user_id:
            wrong += 1
    return present, wrong


def run_traditional(bookings, delay):
    env = dict(os.environ, OLYMPICS_RACE_DELAY=str(delay), OLYMPICS_TICKET_LOCK="0")
    proc = sc.start_server(PORT, env)
    try:
        _fire(lambda b: sc.post_invoke(PORT, "book_ticket",
                                       {"match_id": MATCH, "seat_id": b[0], "user_id": b[1]}),
              bookings)
        state = sc.post_invoke(PORT, "get_state", {})["state"]
    finally:
        sc.stop_server(proc)
    seats = state.get("matches", {}).get(MATCH, {}).get("seats", {})
    return _misattributed(seats, bookings)


def run_faas(bookings, delay):
    from FaaS.storage import reset_state, load_state
    from FaaS import gateway
    reset_state()
    os.environ["OLYMPICS_RACE_DELAY"] = str(delay)
    os.environ["OLYMPICS_FAAS_TXN"] = "1"  # isolate attribution from lost-updates
    _fire(lambda b: gateway.invoke("book_ticket",
                                   {"match_id": MATCH, "seat_id": b[0], "user_id": b[1]}),
          bookings)
    seats = load_state().get("matches", {}).get(MATCH, {}).get("seats", {})
    return _misattributed(seats, bookings)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seats", type=int, default=40, help="concurrent distinct-seat bookings")
    ap.add_argument("--delay", type=float, default=0.01, help="race-window seconds (widens the leak)")
    args = ap.parse_args()
    bookings = _bookings(args.seats)

    print(f"cross-request leak: {args.seats} concurrent bookings, distinct seat + user each, "
          f"race window {args.delay}s\n")

    t_present, t_wrong = run_traditional(bookings, args.delay)
    f_present, f_wrong = run_faas(bookings, args.delay)

    print(f"{'architecture':<16} {'seats present':>14} {'mis-attributed':>16}")
    print("-" * 48)
    print(f"{'Traditional':<16} {t_present:>14} {t_wrong:>16}")
    print(f"{'FaaS':<16} {f_present:>14} {f_wrong:>16}")
    print()
    print(f"Traditional recorded {t_wrong}/{t_present} seats against the WRONG buyer "
          f"(shared _CTX global clobbered across threads).")
    print(f"FaaS mis-attributed {f_wrong} -- process-per-call has no shared request "
          f"context to leak.")


if __name__ == "__main__":
    main()
