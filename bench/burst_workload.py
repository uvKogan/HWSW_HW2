"""
Timestamped, narrative-shaped event timeline for bench/mixed_burst.py.

Unlike common/workload.py (a flat, sequential list replayed one event at a
time for correctness/perf validation), this generates a *scheduled* timeline:
every event carries a "t" (seconds from run start) and a "phase" tag, so a
dispatcher can pace submission against real wall-clock time and produce
scripted bursts layered on background traffic -- one "Games day" compressed
into ~8 seconds:

  background_trickle    0.0 - 8.0s   low-contention ops, spread throughout
  hotel_shuttle_prefill  0.3 - 1.0s   one shuttle filled toward capacity
  streaming_peak         2.0 - 2.5s   a popular match goes live, fans pile on
  hotel_shuttle_spike    2.0 - 2.3s   concurrent boarding race on that shuttle
  ticket_rush_spike      2.5 - 3.0s   ticket-buying spike on the popular match
  live_medal_projection  3.0 - 4.0s   CPU-bound project_medals burst
  wind_down              4.0 - 8.0s   athletes shuttled back, venues released

Every op in common.operations.OPERATIONS appears somewhere (render_highlight
only in its harmless mode -- the corrupt/crash mode is bench/fault_isolation's
job). All IDs are drawn from common.reference_data's fixed roster, exactly
like common/workload.py, except the pinned "popular" match/seats and "hotel"
shuttle, which are pulled from a bounded pool of free-form IDs (match_id,
seat_id, shuttle_id, stream_id are not validated against any roster -- see
common/operations.py) so contention is scripted rather than left to chance.

Run standalone to sanity-check the generated timeline before wiring it into
a dispatcher:

    python -m bench.burst_workload --summary
"""

from __future__ import annotations

import argparse
import json
import random
import sys

from common import reference_data as ref
from common.operations import OPERATIONS

# --- Pinned contention targets (shared across an entire run) ----------------

POPULAR_MATCH = "match_popular"
POPULAR_STREAM = "stream_popular"
POPULAR_SEATS = [f"seat{i}" for i in range(20)]
HOTEL_SHUTTLE_ID = "shuttle_hotel"
HOTEL_SHUTTLE_CAPACITY = 50

# --- Background free-form pools (not roster-validated, but bounded so ops
# collide the way a real bounded Games would -- same idea as workload.py) ---

N_BG_MATCHES = 40
N_BG_SEATS_PER_MATCH = 200  # unused directly here; ticket rush only touches POPULAR_SEATS
N_BG_SHUTTLES = 19  # excludes HOTEL_SHUTTLE_ID
N_BG_STREAMS = 20
RESTAURANTS = ["main_hall", "asia_kitchen", "grill"]

VENUE_IDS = [v["id"] for v in ref.VENUES]
VOLUNTEER_IDS = [v["id"] for v in ref.VOLUNTEERS]
ATHLETE_IDS = [a["id"] for a in ref.ATHLETES]
COUNTRY_CODES = [c["code"] for c in ref.COUNTRIES]
USER_IDS = [f"user{n:03d}" for n in range(200)]

# render_highlight's corrupt/crash mode is bench/fault_isolation.py's job;
# this benchmark only ever calls it in its harmless mode. No op is excluded
# from the "every op gets dispatched at least once" check below -- allocate_stream
# runs only as a side-effect *inside* go_live's cascade in common/operations.py,
# so it also needs a standalone dispatch somewhere (background_trickle) to
# count as independently exercised.


def _bg_match(rng: random.Random) -> str:
    return f"match{rng.randrange(N_BG_MATCHES)}"


def _bg_shuttle(rng: random.Random) -> str:
    return f"shuttle{rng.randrange(N_BG_SHUTTLES)}"


def _bg_stream(rng: random.Random) -> str:
    return f"stream{rng.randrange(N_BG_STREAMS)}"


# --- Per-phase event builders ------------------------------------------------


def _background_trickle(rng: random.Random, count: int, t0: float, t1: float) -> list[dict]:
    ops = [
        "book_venue_slot", "release_venue_slot", "reserve_restaurant_table",
        "assign_volunteer", "dispatch_shuttle", "update_country_score",
        "subscribe_to_updates", "push_live_event", "render_highlight",
        "allocate_stream",
    ]
    events = []
    for _ in range(count):
        op = rng.choice(ops)
        t = rng.uniform(t0, t1)
        if op == "book_venue_slot":
            params = {"venue_id": rng.choice(VENUE_IDS), "match_id": _bg_match(rng)}
        elif op == "release_venue_slot":
            params = {"venue_id": rng.choice(VENUE_IDS)}
        elif op == "reserve_restaurant_table":
            params = {"athlete_id": rng.choice(ATHLETE_IDS),
                      "restaurant_id": rng.choice(RESTAURANTS),
                      "party_size": rng.randint(1, 6)}
        elif op == "assign_volunteer":
            params = {"volunteer_id": rng.choice(VOLUNTEER_IDS), "venue": rng.choice(VENUE_IDS)}
        elif op == "dispatch_shuttle":
            params = {"shuttle_id": _bg_shuttle(rng),
                      "route": f"village->{rng.choice(VENUE_IDS)}",
                      "seats": rng.choice([4, 8, 12, 20])}
        elif op == "update_country_score":
            params = {"country_code": rng.choice(COUNTRY_CODES),
                      "medal": rng.choice(["gold", "silver", "bronze"])}
        elif op == "subscribe_to_updates":
            params = {"subscriber_id": rng.choice(USER_IDS), "topic": _bg_match(rng)}
        elif op == "push_live_event":
            params = {"match_id": _bg_match(rng),
                      "event_type": rng.choice(["start", "score", "finish"]),
                      "details": "auto"}
        elif op == "render_highlight":  # harmless mode only, never corrupt=True
            params = {"match_id": _bg_match(rng)}
        else:  # allocate_stream
            params = {"stream_id": _bg_stream(rng), "match_id": _bg_match(rng)}
        events.append({"t": t, "phase": "background_trickle", "op": op, "params": params})
    return events


def _hotel_shuttle_prefill(rng: random.Random, count: int, t0: float, t1: float) -> list[dict]:
    # Sequential-ish (spread over the window, not concurrent) build-up toward
    # capacity -- boarding sizes chosen so ~count calls land around 80-90% of
    # HOTEL_SHUTTLE_CAPACITY without needing to know the exact running total
    # up front (the op itself rejects any single call that would overshoot).
    per_call = max(1, int(HOTEL_SHUTTLE_CAPACITY * 0.85 / count))
    events = []
    for i in range(count):
        t = t0 + (t1 - t0) * (i / max(1, count))
        params = {"shuttle_id": HOTEL_SHUTTLE_ID, "route": "village->venue",
                  "seats": per_call, "capacity": HOTEL_SHUTTLE_CAPACITY}
        events.append({"t": t, "phase": "hotel_shuttle_prefill", "op": "dispatch_shuttle",
                       "params": params})
    return events


def _hotel_shuttle_spike(rng: random.Random, count: int, t0: float, t1: float) -> list[dict]:
    # Concurrent boarding attempts against the near-full shuttle: each call is
    # small enough that success/failure genuinely depends on scheduling order
    # relative to the other in-flight calls -- the check-then-increment race.
    events = []
    for _ in range(count):
        t = rng.uniform(t0, t1)
        params = {"shuttle_id": HOTEL_SHUTTLE_ID, "route": "village->venue",
                  "seats": rng.choice([2, 3, 4]), "capacity": HOTEL_SHUTTLE_CAPACITY}
        events.append({"t": t, "phase": "hotel_shuttle_spike", "op": "dispatch_shuttle",
                       "params": params})
    return events


def _streaming_peak(rng: random.Random, count: int, t0: float, t1: float) -> list[dict]:
    events = [{"t": t0, "phase": "streaming_peak", "op": "go_live",
              "params": {"match_id": POPULAR_MATCH, "stream_id": POPULAR_STREAM,
                        "details": "final is live"}}]
    remaining = count - 1
    n_subs = int(remaining * 0.7)
    n_pushes = remaining - n_subs
    for _ in range(n_subs):
        t = rng.uniform(t0, t1)
        params = {"subscriber_id": rng.choice(USER_IDS), "topic": POPULAR_MATCH}
        events.append({"t": t, "phase": "streaming_peak", "op": "subscribe_to_updates",
                       "params": params})
    for _ in range(n_pushes):
        t = rng.uniform(t0, t1)
        params = {"match_id": POPULAR_MATCH, "event_type": rng.choice(["score", "highlight"]),
                  "details": "live update"}
        events.append({"t": t, "phase": "streaming_peak", "op": "push_live_event",
                       "params": params})
    return events


def _ticket_rush_spike(rng: random.Random, count: int, t0: float, t1: float) -> list[dict]:
    events = []
    for i in range(count):
        t = rng.uniform(t0, t1)
        params = {"match_id": POPULAR_MATCH,
                  "seat_id": POPULAR_SEATS[i % len(POPULAR_SEATS)],
                  "user_id": rng.choice(USER_IDS)}
        events.append({"t": t, "phase": "ticket_rush_spike", "op": "book_ticket",
                       "params": params})
    return events


def _live_medal_projection(rng: random.Random, count: int, t0: float, t1: float,
                            iterations: int) -> list[dict]:
    events = []
    for i in range(count):
        t = t0 + (t1 - t0) * (i / max(1, count))  # spread evenly, not randomized
        country = COUNTRY_CODES[i % len(COUNTRY_CODES)]
        params = {"country_code": country, "iterations": iterations}
        events.append({"t": t, "phase": "live_medal_projection", "op": "project_medals",
                       "params": params})
    return events


def _wind_down(rng: random.Random, count: int, t0: float, t1: float) -> list[dict]:
    ops = ["dispatch_shuttle", "release_venue_slot", "reserve_restaurant_table",
           "recompute_standings"]
    events = []
    for _ in range(count):
        op = rng.choice(ops)
        t = rng.uniform(t0, t1)
        if op == "dispatch_shuttle":
            params = {"shuttle_id": _bg_shuttle(rng), "route": f"venue->village",
                      "seats": rng.choice([4, 8, 12, 20])}
        elif op == "release_venue_slot":
            params = {"venue_id": rng.choice(VENUE_IDS)}
        elif op == "reserve_restaurant_table":
            params = {"athlete_id": rng.choice(ATHLETE_IDS),
                      "restaurant_id": rng.choice(RESTAURANTS),
                      "party_size": rng.randint(1, 6)}
        else:
            params = {}
        events.append({"t": t, "phase": "wind_down", "op": op, "params": params})
    return events


# --- Phase registry (name -> (builder, t0, t1, base_count)) -----------------
# base_count is the count at --scale 1.0; TOTAL_EVENTS at scale 1.0 is the sum.

_PHASE_SPEC = {
    "background_trickle":   (_background_trickle,   0.0, 8.0, 200),
    "hotel_shuttle_prefill": (_hotel_shuttle_prefill, 0.3, 1.0, 10),
    "streaming_peak":       (_streaming_peak,        2.0, 2.5, 60),
    "hotel_shuttle_spike":  (_hotel_shuttle_spike,   2.0, 2.3, 18),
    "ticket_rush_spike":    (_ticket_rush_spike,     2.5, 3.0, 150),
    # live_medal_projection is the one honest FaaS-wins-under-load axis (pure
    # CPU, no shared state -- see common/operations.py:project_medals): 150
    # calls (not 64) so "hundreds" of genuinely parallel requests actually
    # land here, not just in the contention-heavy phases where more volume
    # would only make Traditional's in-memory-no-subprocess-tax advantage
    # bigger, not FaaS's.
    "live_medal_projection": (_live_medal_projection, 3.0, 4.0, 150),
    "wind_down":            (_wind_down,             4.0, 8.0, 60),
}

TOTAL_EVENTS_AT_SCALE_1 = sum(spec[3] for spec in _PHASE_SPEC.values())  # 648


def generate_timeline(seed: int = 42, scale: float = 1.0,
                       medal_iterations: int = 2_000_000) -> list[dict]:
    """Return a time-sorted list of {"t", "phase", "op", "params"} events.

    `scale` shrinks/grows both event counts AND each phase's time window by
    the same factor, so burst *density* (events/second within a phase) stays
    constant -- a reduced-scale smoke test still exercises real concurrent
    bursts, just compressed into a shorter run, instead of thinning events
    out across an unchanged window (which would dilute concurrency away and
    make small-scale timing meaningless).
    """
    rng = random.Random(seed)
    events: list[dict] = []
    for phase, (builder, t0, t1, base_count) in _PHASE_SPEC.items():
        count = max(1, round(base_count * scale))
        st0, st1 = t0 * scale, t1 * scale
        if builder is _live_medal_projection:
            events.extend(builder(rng, count, st0, st1, medal_iterations))
        else:
            events.extend(builder(rng, count, st0, st1))
    events.sort(key=lambda e: e["t"])
    return events


# --- Standalone summary / self-check ----------------------------------------


def _summarize(events: list[dict]) -> dict:
    by_phase: dict[str, list[dict]] = {}
    by_op: dict[str, int] = {}
    for e in events:
        by_phase.setdefault(e["phase"], []).append(e)
        by_op[e["op"]] = by_op.get(e["op"], 0) + 1

    phase_windows = {}
    for phase, evs in by_phase.items():
        ts = [e["t"] for e in evs]
        phase_windows[phase] = {"count": len(evs), "t_min": min(ts), "t_max": max(ts)}

    missing_ops = set(OPERATIONS) - set(by_op)

    popular_match_ok = all(
        e["params"].get("match_id") == POPULAR_MATCH or e["params"].get("topic") == POPULAR_MATCH
        for e in by_phase.get("streaming_peak", [])
    )
    popular_seats_ok = all(
        e["params"]["seat_id"] in POPULAR_SEATS and e["params"]["match_id"] == POPULAR_MATCH
        for e in by_phase.get("ticket_rush_spike", [])
    )
    hotel_shuttle_ok = all(
        e["params"]["shuttle_id"] == HOTEL_SHUTTLE_ID
        for e in by_phase.get("hotel_shuttle_spike", []) + by_phase.get("hotel_shuttle_prefill", [])
    )

    return {
        "total_events": len(events),
        "by_phase": phase_windows,
        "by_op": dict(sorted(by_op.items())),
        "missing_ops": sorted(missing_ops),
        "popular_match_pinned_ok": popular_match_ok,
        "popular_seats_pinned_ok": popular_seats_ok,
        "hotel_shuttle_pinned_ok": hotel_shuttle_ok,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--scale", type=float, default=1.0)
    ap.add_argument("--iterations", type=int, default=2_000_000,
                    help="project_medals iterations per call in the medal-projection phase")
    ap.add_argument("--summary", action="store_true", help="print a human-readable summary")
    ap.add_argument("--dump", type=str, help="write the full timeline to this JSON path")
    args = ap.parse_args()

    events = generate_timeline(seed=args.seed, scale=args.scale, medal_iterations=args.iterations)

    if args.dump:
        with open(args.dump, "w") as f:
            json.dump(events, f, indent=2)
        print(f"wrote {len(events)} events to {args.dump}")

    if args.summary or not args.dump:
        summary = _summarize(events)
        print(json.dumps(summary, indent=2))
        if summary["missing_ops"]:
            print(f"\nWARNING: ops never exercised: {summary['missing_ops']}", file=sys.stderr)
            sys.exit(1)
        if not (summary["popular_match_pinned_ok"] and summary["popular_seats_pinned_ok"]
                and summary["hotel_shuttle_pinned_ok"]):
            print("\nWARNING: pinned-target check failed", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
