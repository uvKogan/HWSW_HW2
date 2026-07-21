"""
Deterministic workload generator shared by both architectures.

Both Traditional/server.py and FaaS/gateway.py replay the exact same event
sequence, so Part 4's performance comparison is driven by identical work,
and the final states can be diffed for a correctness check (same inputs ->
same observable outputs, regardless of execution architecture).

IDs are drawn from `common.reference_data`'s fixed roster so a replayed
workload looks like a real, bounded Games rather than unbounded synthetic
IDs. The generator emits the 9 base ops plus the Part 3 `go_live` cascade.
`project_medals` is deliberately excluded -- it is exercised only by the
parallel-throughput benchmark, not the correctness/perf replay.
"""

import json
import random
import sys
from pathlib import Path

from common import reference_data as ref

# Small bounded pools so ops actually collide (venues get re-booked, seats
# get re-sold, standings accumulate) rather than every event touching a fresh
# unique ID.
VENUE_IDS = [v["id"] for v in ref.VENUES]
VOLUNTEER_IDS = [v["id"] for v in ref.VOLUNTEERS]
ATHLETE_IDS = [a["id"] for a in ref.ATHLETES]
COUNTRY_CODES = [c["code"] for c in ref.COUNTRIES]
# Pools sized so a multi-thousand-event replay builds up a substantial state
# blob (many matches, each with many sold seats, plus subscriptions and
# bookings) -- that growing state is what makes the FaaS reload-per-call cost
# visible in bench/state_growth.py. Bounded enough that ops still collide.
N_MATCHES = 60
N_SEATS = 300
N_SHUTTLES = 30
N_STREAMS = 60
N_USERS = 500  # the full spectator pool is active in a run

OP_NAMES = [
    "book_venue_slot", "release_venue_slot", "book_ticket", "assign_volunteer",
    "dispatch_shuttle", "reserve_restaurant_table", "subscribe_to_updates",
    "push_live_event", "update_country_score", "go_live",
]


def _params_for(op: str, rng: random.Random) -> dict:
    match = f"match{rng.randrange(N_MATCHES)}"
    if op == "book_venue_slot":
        return {"venue_id": rng.choice(VENUE_IDS), "match_id": match}
    if op == "release_venue_slot":
        return {"venue_id": rng.choice(VENUE_IDS)}
    if op == "book_ticket":
        return {"match_id": match, "seat_id": f"seat{rng.randrange(N_SEATS)}",
                "user_id": f"user{rng.randrange(N_USERS):03d}"}
    if op == "assign_volunteer":
        return {"volunteer_id": rng.choice(VOLUNTEER_IDS), "venue": rng.choice(VENUE_IDS)}
    if op == "dispatch_shuttle":
        return {"shuttle_id": f"shuttle{rng.randrange(N_SHUTTLES)}",
                "route": f"village->{rng.choice(VENUE_IDS)}",
                "seats": rng.choice([4, 8, 12, 20])}
    if op == "reserve_restaurant_table":
        return {"athlete_id": rng.choice(ATHLETE_IDS),
                "restaurant_id": rng.choice(["main_hall", "asia_kitchen", "grill"]),
                "party_size": rng.randint(1, 6)}
    if op == "subscribe_to_updates":
        return {"subscriber_id": f"user{rng.randrange(N_USERS):03d}", "topic": match}
    if op == "push_live_event":
        return {"match_id": match, "event_type": rng.choice(["start", "score", "finish"]),
                "details": "auto"}
    if op == "update_country_score":
        return {"country_code": rng.choice(COUNTRY_CODES),
                "medal": rng.choice(["gold", "silver", "bronze"])}
    if op == "go_live":
        return {"match_id": match, "venue_id": rng.choice(VENUE_IDS),
                "stream_id": f"stream{rng.randrange(N_STREAMS)}"}
    raise ValueError(f"no param generator wired up for operation {op!r}")


def generate_workload(seed: int = 42, n_events: int = 2000) -> list[dict]:
    rng = random.Random(seed)
    events = []
    for _ in range(n_events):
        op = rng.choice(OP_NAMES)
        events.append({"op": op, "params": _params_for(op, rng)})
    return events


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    n_events = int(sys.argv[2]) if len(sys.argv) > 2 else 2000
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("common/workload_fixture.json")

    events = generate_workload(seed=seed, n_events=n_events)
    out_path.write_text(json.dumps(events, indent=2))
    print(f"wrote {len(events)} events to {out_path}")


if __name__ == "__main__":
    main()
