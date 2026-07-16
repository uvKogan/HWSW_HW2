"""
Shared business logic for both architectures: the Olympic Games Management
System.

Every operation has the same contract:

    operation(state: dict, params: dict) -> dict (result)

and mutates `state` in place. Both Traditional/services/* and
FaaS/functions/* call the SAME functions here -- the only thing that differs
between the two architectures is how `state` is obtained (persistent
in-memory object vs. loaded/saved per call) and how the call is dispatched
(in-process function call vs. subprocess-per-call).

Entity IDs are validated against the fixed roster in
`common.reference_data`. State is kept JSON-clean (string dict keys, lists
not tuples, no sets) so the FaaS side's sqlite JSON round-trip produces a
state identical to Traditional's in-memory copy -- the correctness gate
(`common.compare_states`) relies on this.

Operation groups:
  - 9 base ops (Parts 1 & 2), exercised by the deterministic workload.
  - Part 3 feature: `allocate_stream`, `recompute_standings`, `go_live`
    (a cross-cutting cascade composed of the first two + `push_live_event`).
  - `project_medals`: a CPU-bound, independent, read-only op used only by
    the parallel-throughput benchmark (the FaaS-wins axis).
"""

import os
import time
from datetime import datetime, timezone

from common import reference_data as ref

MEDAL_POINTS = {"gold": 3, "silver": 2, "bronze": 1}


def _race_window() -> None:
    """Demo-only hook: widen the check-then-commit window in book_ticket so
    the seat-booking race is reproducible in bench/seat_race.py.

    Default is a no-op (env unset → 0s), so normal correctness/perf runs are
    completely unaffected. A real ticketing system has genuine latency here (a
    DB round-trip between "is the seat free?" and "mark it sold"); this just
    makes that inherent window observable on demand.
    """
    delay = float(os.environ.get("OLYMPICS_RACE_DELAY", "0") or 0)
    if delay:
        time.sleep(delay)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(state: dict, event: str, **fields) -> None:
    state.setdefault("log", []).append({"ts": _now(), "event": event, **fields})


def _reject(state: dict, event: str, message: str, **fields) -> dict:
    _log(state, event + "_rejected", **fields)
    return {"ok": False, "message": message}


# --- Base operations (Parts 1 & 2) -----------------------------------------


def book_venue_slot(state: dict, params: dict) -> dict:
    """Reserve a venue for a competition session; deny if already occupied."""
    venue_id = params["venue_id"]
    match_id = params["match_id"]
    if venue_id not in ref.VENUE_IDS:
        return _reject(state, "book_venue_slot", f"unknown venue {venue_id}", venue_id=venue_id)

    venues = state.setdefault("venues", {})
    venue = venues.setdefault(venue_id, {"status": "free", "held_by": None})
    if venue["status"] != "free":
        return _reject(state, "book_venue_slot", f"venue {venue_id} not free",
                       venue_id=venue_id, match_id=match_id)

    venue["status"] = "occupied"
    venue["held_by"] = match_id
    _log(state, "book_venue_slot", venue_id=venue_id, match_id=match_id)
    return {"ok": True, "message": f"venue {venue_id} booked for {match_id}"}


def release_venue_slot(state: dict, params: dict) -> dict:
    """Release a previously booked venue back to the free pool."""
    venue_id = params["venue_id"]
    venue = state.setdefault("venues", {}).get(venue_id)
    if venue is None or venue["status"] == "free":
        return _reject(state, "release_venue_slot", f"venue {venue_id} was not occupied",
                       venue_id=venue_id)

    venue["status"] = "free"
    venue["held_by"] = None
    _log(state, "release_venue_slot", venue_id=venue_id)
    return {"ok": True, "message": f"venue {venue_id} released"}


def book_ticket(state: dict, params: dict) -> dict:
    """Reserve one specific seat for a match; deny if that seat is sold.

    Seat-level (not a counter): the interesting race is two buyers both
    seeing the same seat as free. The check-then-assign below is the
    critical section the concurrency benchmark stresses.
    """
    match_id = params["match_id"]
    seat_id = params["seat_id"]
    user_id = params["user_id"]
    if user_id not in ref.USER_IDS:
        return _reject(state, "book_ticket", f"unknown user {user_id}",
                       match_id=match_id, seat_id=seat_id, user_id=user_id)

    match = state.setdefault("matches", {}).setdefault(match_id, {"venue_id": None, "seats": {}})
    seats = match["seats"]
    if seat_id in seats:
        return _reject(state, "book_ticket", f"seat {seat_id} already sold",
                       match_id=match_id, seat_id=seat_id, user_id=user_id)

    _race_window()  # no-op unless OLYMPICS_RACE_DELAY is set (seat-race demo)
    seats[seat_id] = user_id
    _log(state, "book_ticket", match_id=match_id, seat_id=seat_id, user_id=user_id)
    return {"ok": True, "message": f"seat {seat_id} sold to {user_id}"}


def assign_volunteer(state: dict, params: dict) -> dict:
    """Assign a volunteer to a venue."""
    volunteer_id = params["volunteer_id"]
    venue = params["venue"]
    if volunteer_id not in ref.VOLUNTEER_IDS:
        return _reject(state, "assign_volunteer", f"unknown volunteer {volunteer_id}",
                       volunteer_id=volunteer_id)
    if venue not in ref.VENUE_IDS:
        return _reject(state, "assign_volunteer", f"unknown venue {venue}",
                       volunteer_id=volunteer_id, venue=venue)

    state.setdefault("volunteers", {})[volunteer_id] = {"venue": venue}
    _log(state, "assign_volunteer", volunteer_id=volunteer_id, venue=venue)
    return {"ok": True, "message": f"volunteer {volunteer_id} assigned to {venue}"}


def dispatch_shuttle(state: dict, params: dict) -> dict:
    """Assign a shuttle to a route and board passengers against a seat ceiling."""
    shuttle_id = params["shuttle_id"]
    route = params["route"]
    boarding = int(params.get("seats", 0))
    capacity = int(params.get("capacity", 50))

    shuttles = state.setdefault("shuttles", {})
    shuttle = shuttles.setdefault(shuttle_id, {"route": route, "passengers": 0, "capacity": capacity})
    shuttle["route"] = route
    new_load = shuttle["passengers"] + boarding
    if new_load > shuttle["capacity"]:
        return _reject(state, "dispatch_shuttle", f"shuttle {shuttle_id} over capacity",
                       shuttle_id=shuttle_id, route=route)

    shuttle["passengers"] = new_load
    _log(state, "dispatch_shuttle", shuttle_id=shuttle_id, route=route, passengers=new_load)
    return {"ok": True, "message": f"shuttle {shuttle_id} on {route} ({new_load} aboard)"}


def reserve_restaurant_table(state: dict, params: dict) -> dict:
    """Reserve a dining slot for an athlete at a village restaurant."""
    athlete_id = params["athlete_id"]
    restaurant_id = params["restaurant_id"]
    party_size = int(params["party_size"])
    if athlete_id not in ref.ATHLETE_IDS:
        return _reject(state, "reserve_restaurant_table", f"unknown athlete {athlete_id}",
                       athlete_id=athlete_id)
    if not 1 <= party_size <= 8:
        return _reject(state, "reserve_restaurant_table", "party size out of range (1-8)",
                       athlete_id=athlete_id, party_size=party_size)

    key = f"{restaurant_id}:{athlete_id}"
    state.setdefault("restaurant_bookings", {})[key] = {
        "athlete_id": athlete_id, "restaurant_id": restaurant_id, "party_size": party_size,
    }
    _log(state, "reserve_restaurant_table", athlete_id=athlete_id, restaurant_id=restaurant_id)
    return {"ok": True, "message": f"table for {party_size} reserved for {athlete_id}"}


def subscribe_to_updates(state: dict, params: dict) -> dict:
    """Register a spectator's interest in a topic's live updates (pub/sub)."""
    subscriber_id = params["subscriber_id"]
    topic = params["topic"]
    if subscriber_id not in ref.USER_IDS:
        return _reject(state, "subscribe_to_updates", f"unknown subscriber {subscriber_id}",
                       subscriber_id=subscriber_id, topic=topic)

    subs = state.setdefault("subscriptions", {}).setdefault(topic, [])
    if subscriber_id not in subs:
        subs.append(subscriber_id)
    _log(state, "subscribe_to_updates", subscriber_id=subscriber_id, topic=topic)
    return {"ok": True, "message": f"{subscriber_id} subscribed to {topic}"}


def push_live_event(state: dict, params: dict) -> dict:
    """Push a live update for a match, fanning it out to its subscribers."""
    match_id = params["match_id"]
    event_type = params["event_type"]
    details = params.get("details", "")

    match = state.setdefault("matches", {}).setdefault(match_id, {"venue_id": None, "seats": {}})
    match["status"] = event_type

    subscribers = state.setdefault("subscriptions", {}).get(match_id, [])
    for sub in subscribers:
        _log(state, "delivery", topic=match_id, delivered_to=sub, event_type=event_type)
    _log(state, "push_live_event", match_id=match_id, event_type=event_type, details=details)
    return {"ok": True, "message": f"pushed {event_type} for {match_id}",
            "delivered": len(subscribers)}


def update_country_score(state: dict, params: dict) -> dict:
    """Adjust a country's medal tally."""
    country_code = params["country_code"]
    medal = params["medal"]
    if country_code not in ref.COUNTRY_CODES:
        return _reject(state, "update_country_score", f"unknown country {country_code}",
                       country_code=country_code)
    if medal not in MEDAL_POINTS:
        return _reject(state, "update_country_score", f"unknown medal {medal}",
                       country_code=country_code, medal=medal)

    scores = state.setdefault("country_scores", {})
    entry = scores.setdefault(country_code, {"gold": 0, "silver": 0, "bronze": 0, "points": 0})
    entry[medal] += 1
    entry["points"] += MEDAL_POINTS[medal]
    _log(state, "update_country_score", country_code=country_code, medal=medal)
    return {"ok": True, "message": f"{country_code} +1 {medal}", "points": entry["points"]}


# --- Part 3 feature: go_live cascade ---------------------------------------


def allocate_stream(state: dict, params: dict) -> dict:
    """Put a broadcast stream on air for a match (the 'livestreaming' piece)."""
    stream_id = params["stream_id"]
    match_id = params["match_id"]
    state.setdefault("streams", {})[stream_id] = {"match_id": match_id, "status": "on_air"}
    _log(state, "allocate_stream", stream_id=stream_id, match_id=match_id)
    return {"ok": True, "message": f"stream {stream_id} on air for {match_id}"}


def recompute_standings(state: dict, params: dict) -> dict:
    """Deterministically recompute the ranked medal standings from country_scores.

    A whole-state read: naturally exposes the FaaS side's reload cost. The
    output is a pure function of country_scores (no timestamp/RNG) so both
    architectures produce identical standings.
    """
    scores = state.setdefault("country_scores", {})
    ranking = [
        {"country": code, "gold": s["gold"], "silver": s["silver"],
         "bronze": s["bronze"], "points": s["points"]}
        for code, s in scores.items()
    ]
    # Sort by points, then golds, then code -- all deterministic tie-breakers.
    ranking.sort(key=lambda r: (-r["points"], -r["gold"], -r["silver"], r["country"]))
    for rank, row in enumerate(ranking, start=1):
        row["rank"] = rank
    state["standings"] = {"ranking": ranking}
    _log(state, "recompute_standings", countries=len(ranking))
    return {"ok": True, "message": f"standings recomputed for {len(ranking)} countries"}


def go_live(state: dict, params: dict) -> dict:
    """Cross-cutting cascade fired when a match goes live: announce -> stream
    -> recompute standings. One atomic in-process business transaction in the
    Traditional architecture; see FaaS/orchestrators/go_live_chain.py for the
    FaaS decomposition that has to chain three isolated calls instead."""
    match_id = params["match_id"]
    stream_id = params["stream_id"]

    push_live_event(state, {"match_id": match_id, "event_type": "live",
                            "details": params.get("details", "match is live")})
    allocate_stream(state, {"stream_id": stream_id, "match_id": match_id})
    recompute_standings(state, {})
    _log(state, "go_live", match_id=match_id, stream_id=stream_id)
    return {"ok": True, "message": f"{match_id} is live on {stream_id}"}


# --- Parallel-throughput benchmark op (NOT in the correctness workload) -----


def project_medals(state: dict, params: dict) -> dict:
    """CPU-bound, independent, read-only Monte Carlo medal projection.

    Ignores `state` entirely and writes nothing -- so concurrent invocations
    never contend, which is exactly the embarrassingly-parallel case where
    FaaS's process-per-call model beats the single GIL-bound monolith. Pure
    Python on purpose: the GIL-serialized CPU work is what makes the FaaS
    parallel win visible. `iterations` tunes the per-call cost.
    """
    country = params["country_code"]
    iterations = int(params.get("iterations", 200_000))
    # Deterministic LCG seeded from the country code; count "gold" outcomes.
    x = sum(ord(c) for c in country) or 1
    gold = 0
    for _ in range(iterations):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        if x % 1000 < 5:
            gold += 1
    return {"ok": True, "country": country, "iterations": iterations, "projected_gold": gold}


# Registry used by both architectures' dispatch layers.
OPERATIONS = {
    # base (in the deterministic workload)
    "book_venue_slot": book_venue_slot,
    "release_venue_slot": release_venue_slot,
    "book_ticket": book_ticket,
    "assign_volunteer": assign_volunteer,
    "dispatch_shuttle": dispatch_shuttle,
    "reserve_restaurant_table": reserve_restaurant_table,
    "subscribe_to_updates": subscribe_to_updates,
    "push_live_event": push_live_event,
    "update_country_score": update_country_score,
    # Part 3 cascade + its decomposable steps
    "allocate_stream": allocate_stream,
    "recompute_standings": recompute_standings,
    "go_live": go_live,
    # parallel-throughput benchmark (not in the workload)
    "project_medals": project_medals,
}


def initial_state() -> dict:
    return {
        "venues": {},
        "matches": {},
        "volunteers": {},
        "shuttles": {},
        "restaurant_bookings": {},
        "subscriptions": {},
        "country_scores": {},
        "standings": {},
        "streams": {},
        "log": [],
    }
