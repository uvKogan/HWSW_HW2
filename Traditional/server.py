"""
Traditional architecture -- the WHOLE thing, in one file.

This is deliberately a *naive monolith*: one long-lived process, all state in
module-level globals, and every operation's logic inlined into a single giant
`handle()` dispatcher. There is no shared `common.operations` core here (unlike
FaaS): the business logic lives right here, tangled together, with validation
copy-pasted at each call site and magic numbers sprinkled inline. This is the
realistic "path of least resistance" first draft a team writes when nothing in
the architecture *forces* them to decouple -- which is exactly the point of the
report's comparison. See PROJECT.md / the report for why we wrote it this way.

Traits this file demonstrates (all load-bearing for Part 4):
  * Shared mutable memory: all requests mutate the same global dicts. Fast
    (O(1), no serialization) but a minefield under concurrency.
  * No persistence: state lives only in this process. Cheap, but a crash
    (see the `render_highlight` op) loses *everything*.
  * A documented concurrency bug: `_CTX` holds "the current request's actor"
    in a module global. Correct single-threaded; under the ThreadingHTTPServer
    two overlapping requests clobber it, so a seat can be recorded against the
    wrong buyer (cross-request state leak). FaaS's process-per-call model makes
    this class of bug impossible. See bench/context_leak.py.
  * A single GIL-bound process: CPU-bound ops (project_medals) can't use more
    than ~one core. See bench/parallel_throughput.py.

Run modes (same CLI the benchmarks and script.sh expect):
    python3 -m Traditional.server --serve [--port 8080]
    python3 -m Traditional.server --workload path/to/events.json
"""

import argparse
import json
import os
import sys
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from common import reference_data as ref

# --- The entire application state, as module-level globals (no persistence) --
VENUES = {}
MATCHES = {}
VOLUNTEERS = {}
SHUTTLES = {}
RESTAURANTS = {}
SUBSCRIPTIONS = {}
SCORES = {}
STANDINGS = {}
STREAMS = {}
LOG = []

# "Current request context" stashed in a global -- the naive way to pass the
# acting user around without threading it through every function. This is the
# seed of the documented cross-request leak bug (see module docstring).
_CTX = {"actor": "system"}

# Optional coarse lock, off by default (the naive default). bench/seat_race.py
# flips OLYMPICS_TICKET_LOCK=1 to show the "just add a lock" monolith fix.
_LOCK = threading.Lock()

_MEDAL_POINTS = {"gold": 3, "silver": 2, "bronze": 1}


def _lock_enabled():
    return os.environ.get("OLYMPICS_TICKET_LOCK", "0") not in ("", "0")


def _race_window():
    """Inherent check-then-write latency window (a real ticketing system has a
    DB round-trip here). Widened on demand via OLYMPICS_RACE_DELAY so both the
    seat-oversell race and the _CTX leak are reproducible in the benchmarks."""
    delay = float(os.environ.get("OLYMPICS_RACE_DELAY", "0") or 0)
    if delay:
        time.sleep(delay)


def _log(event, **fields):
    LOG.append({"ts": datetime.now(timezone.utc).isoformat(), "event": event, **fields})


def reset_state():
    """Wipe all state (used by the unit tests between cases)."""
    for d in (VENUES, MATCHES, VOLUNTEERS, SHUTTLES, RESTAURANTS,
              SUBSCRIPTIONS, SCORES, STANDINGS, STREAMS):
        d.clear()
    LOG.clear()
    _CTX["actor"] = "system"


def snapshot():
    """A plain dict copy of the whole state (for --workload dumps and reads)."""
    return {
        "venues": VENUES, "matches": MATCHES, "volunteers": VOLUNTEERS,
        "shuttles": SHUTTLES, "restaurant_bookings": RESTAURANTS,
        "subscriptions": SUBSCRIPTIONS, "country_scores": SCORES,
        "standings": STANDINGS, "streams": STREAMS, "log": LOG,
    }


def _dispatch(op, params):
    """One giant if/elif with all the business logic inlined. No factoring, no
    shared helpers to speak of -- the monolith grew this way."""
    # Stash the acting principal for this request in the global context. Every
    # branch below may read it. (This is the naive design the report critiques.)
    _CTX["actor"] = params.get("user_id") or params.get("subscriber_id") \
        or params.get("volunteer_id") or params.get("athlete_id") or "system"

    if op == "book_venue_slot":
        venue_id = params["venue_id"]
        match_id = params["match_id"]
        if venue_id not in ref.VENUE_IDS:  # inline validation (copy #1)
            _log("book_venue_slot_rejected", venue_id=venue_id)
            return {"ok": False, "message": f"unknown venue {venue_id}"}
        v = VENUES.setdefault(venue_id, {"status": "free", "held_by": None})
        if v["status"] != "free":
            _log("book_venue_slot_rejected", venue_id=venue_id, match_id=match_id)
            return {"ok": False, "message": f"venue {venue_id} not free"}
        v["status"] = "occupied"
        v["held_by"] = match_id
        _log("book_venue_slot", venue_id=venue_id, match_id=match_id)
        return {"ok": True, "message": f"venue {venue_id} booked for {match_id}"}

    elif op == "release_venue_slot":
        venue_id = params["venue_id"]
        v = VENUES.get(venue_id)
        if v is None or v["status"] == "free":
            _log("release_venue_slot_rejected", venue_id=venue_id)
            return {"ok": False, "message": f"venue {venue_id} was not occupied"}
        v["status"] = "free"
        v["held_by"] = None
        _log("release_venue_slot", venue_id=venue_id)
        return {"ok": True, "message": f"venue {venue_id} released"}

    elif op == "book_ticket":
        match_id = params["match_id"]
        seat_id = params["seat_id"]
        user_id = params["user_id"]
        if user_id not in ref.USER_IDS:  # inline validation (copy #2)
            _log("book_ticket_rejected", seat_id=seat_id, user_id=user_id)
            return {"ok": False, "message": f"unknown user {user_id}"}
        m = MATCHES.setdefault(match_id, {"venue_id": None, "seats": {}})
        if seat_id in m["seats"]:
            _log("book_ticket_rejected", match_id=match_id, seat_id=seat_id)
            return {"ok": False, "message": f"seat {seat_id} already sold"}
        _race_window()  # check-then-write gap
        # BUG (documented): record the seat against the *global* current actor
        # rather than the local `user_id`. Identical single-threaded; under the
        # threaded server an overlapping request has overwritten _CTX, so the
        # seat gets attributed to the wrong buyer. FaaS can't reach this state.
        m["seats"][seat_id] = _CTX["actor"]
        _log("book_ticket", match_id=match_id, seat_id=seat_id, user_id=user_id)
        return {"ok": True, "message": f"seat {seat_id} sold to {user_id}"}

    elif op == "assign_volunteer":
        volunteer_id = params["volunteer_id"]
        venue = params["venue"]
        if volunteer_id not in ref.VOLUNTEER_IDS:
            _log("assign_volunteer_rejected", volunteer_id=volunteer_id)
            return {"ok": False, "message": f"unknown volunteer {volunteer_id}"}
        if venue not in ref.VENUE_IDS:  # inline validation (copy #3)
            _log("assign_volunteer_rejected", volunteer_id=volunteer_id, venue=venue)
            return {"ok": False, "message": f"unknown venue {venue}"}
        VOLUNTEERS[volunteer_id] = {"venue": venue}
        _log("assign_volunteer", volunteer_id=volunteer_id, venue=venue)
        return {"ok": True, "message": f"volunteer {volunteer_id} assigned to {venue}"}

    elif op == "dispatch_shuttle":
        shuttle_id = params["shuttle_id"]
        route = params["route"]
        boarding = int(params.get("seats", 0))
        capacity = int(params.get("capacity", 50))  # magic default, inline
        s = SHUTTLES.setdefault(shuttle_id, {"route": route, "passengers": 0, "capacity": capacity})
        s["route"] = route
        if s["passengers"] + boarding > s["capacity"]:
            _log("dispatch_shuttle_rejected", shuttle_id=shuttle_id, route=route)
            return {"ok": False, "message": f"shuttle {shuttle_id} over capacity"}
        s["passengers"] = s["passengers"] + boarding
        _log("dispatch_shuttle", shuttle_id=shuttle_id, route=route, passengers=s["passengers"])
        return {"ok": True, "message": f"shuttle {shuttle_id} on {route} ({s['passengers']} aboard)"}

    elif op == "reserve_restaurant_table":
        athlete_id = params["athlete_id"]
        restaurant_id = params["restaurant_id"]
        party_size = int(params["party_size"])
        if athlete_id not in ref.ATHLETE_IDS:
            _log("reserve_restaurant_table_rejected", athlete_id=athlete_id)
            return {"ok": False, "message": f"unknown athlete {athlete_id}"}
        if party_size < 1 or party_size > 8:  # magic bounds, inline
            _log("reserve_restaurant_table_rejected", athlete_id=athlete_id, party_size=party_size)
            return {"ok": False, "message": "party size out of range (1-8)"}
        RESTAURANTS[f"{restaurant_id}:{athlete_id}"] = {
            "athlete_id": athlete_id, "restaurant_id": restaurant_id, "party_size": party_size}
        _log("reserve_restaurant_table", athlete_id=athlete_id, restaurant_id=restaurant_id)
        return {"ok": True, "message": f"table for {party_size} reserved for {athlete_id}"}

    elif op == "subscribe_to_updates":
        subscriber_id = params["subscriber_id"]
        topic = params["topic"]
        if subscriber_id not in ref.USER_IDS:
            _log("subscribe_to_updates_rejected", subscriber_id=subscriber_id, topic=topic)
            return {"ok": False, "message": f"unknown subscriber {subscriber_id}"}
        subs = SUBSCRIPTIONS.setdefault(topic, [])
        if subscriber_id not in subs:
            subs.append(subscriber_id)
        _log("subscribe_to_updates", subscriber_id=subscriber_id, topic=topic)
        return {"ok": True, "message": f"{subscriber_id} subscribed to {topic}"}

    elif op == "push_live_event":
        match_id = params["match_id"]
        event_type = params["event_type"]
        details = params.get("details", "")
        m = MATCHES.setdefault(match_id, {"venue_id": None, "seats": {}})
        m["status"] = event_type
        subs = SUBSCRIPTIONS.get(match_id, [])
        for sub in subs:
            _log("delivery", topic=match_id, delivered_to=sub, event_type=event_type)
        _log("push_live_event", match_id=match_id, event_type=event_type, details=details)
        return {"ok": True, "message": f"pushed {event_type} for {match_id}", "delivered": len(subs)}

    elif op == "update_country_score":
        country_code = params["country_code"]
        medal = params["medal"]
        if country_code not in ref.COUNTRY_CODES:
            _log("update_country_score_rejected", country_code=country_code)
            return {"ok": False, "message": f"unknown country {country_code}"}
        if medal not in _MEDAL_POINTS:
            _log("update_country_score_rejected", country_code=country_code, medal=medal)
            return {"ok": False, "message": f"unknown medal {medal}"}
        e = SCORES.setdefault(country_code, {"gold": 0, "silver": 0, "bronze": 0, "points": 0})
        e[medal] += 1
        e["points"] += _MEDAL_POINTS[medal]
        _log("update_country_score", country_code=country_code, medal=medal)
        return {"ok": True, "message": f"{country_code} +1 {medal}", "points": e["points"]}

    elif op == "allocate_stream":
        stream_id = params["stream_id"]
        match_id = params["match_id"]
        STREAMS[stream_id] = {"match_id": match_id, "status": "on_air"}
        _log("allocate_stream", stream_id=stream_id, match_id=match_id)
        return {"ok": True, "message": f"stream {stream_id} on air for {match_id}"}

    elif op == "recompute_standings":
        # Rebuilt from scratch each call, inline (no shared helper).
        ranking = []
        for code, s in SCORES.items():
            ranking.append({"country": code, "gold": s["gold"], "silver": s["silver"],
                            "bronze": s["bronze"], "points": s["points"]})
        ranking.sort(key=lambda r: (-r["points"], -r["gold"], -r["silver"], r["country"]))
        for i, row in enumerate(ranking, start=1):
            row["rank"] = i
        STANDINGS["ranking"] = ranking
        _log("recompute_standings", countries=len(ranking))
        return {"ok": True, "message": f"standings recomputed for {len(ranking)} countries"}

    elif op == "go_live":
        # The cross-cutting cascade, inlined as one atomic block (announce ->
        # stream -> recompute). In the monolith this is trivially atomic and
        # cheap -- the one axis where the monolith genuinely wins.
        match_id = params["match_id"]
        stream_id = params["stream_id"]
        m = MATCHES.setdefault(match_id, {"venue_id": None, "seats": {}})
        m["status"] = "live"
        subs = SUBSCRIPTIONS.get(match_id, [])
        for sub in subs:
            _log("delivery", topic=match_id, delivered_to=sub, event_type="live")
        STREAMS[stream_id] = {"match_id": match_id, "status": "on_air"}
        ranking = []
        for code, s in SCORES.items():
            ranking.append({"country": code, "gold": s["gold"], "silver": s["silver"],
                            "bronze": s["bronze"], "points": s["points"]})
        ranking.sort(key=lambda r: (-r["points"], -r["gold"], -r["silver"], r["country"]))
        for i, row in enumerate(ranking, start=1):
            row["rank"] = i
        STANDINGS["ranking"] = ranking
        _log("go_live", match_id=match_id, stream_id=stream_id)
        return {"ok": True, "message": f"{match_id} is live on {stream_id}"}

    elif op == "project_medals":
        # CPU-bound, in-process. One GIL-bound interpreter -> ~one core even
        # with the ThreadingHTTPServer. Same LCG as the FaaS side.
        country = params["country_code"]
        iterations = int(params.get("iterations", 200_000))
        x = sum(ord(c) for c in country) or 1
        gold = 0
        for _ in range(iterations):
            x = (1103515245 * x + 12345) & 0x7FFFFFFF
            if x % 1000 < 5:
                gold += 1
        return {"ok": True, "country": country, "iterations": iterations, "projected_gold": gold}

    elif op == "render_highlight":
        # Poison op: a native-level crash (segfault/OOM), modeled as os.abort().
        # In this monolith it kills the shared process and every global above
        # with it. See bench/fault_isolation.py.
        if params.get("corrupt"):
            os.abort()
        return {"ok": True, "message": f"highlight reel rendered for {params.get('match_id', '?')}"}

    elif op == "get_state":
        # Read-only introspection endpoint the benchmarks use to inspect the
        # in-memory state over HTTP.
        return {"ok": True, "state": snapshot()}

    else:
        return {"ok": False, "message": f"unknown operation {op!r}"}


def handle(op, params):
    """Public entry point. Holds the coarse lock iff OLYMPICS_TICKET_LOCK is set."""
    if _lock_enabled():
        with _LOCK:
            return _dispatch(op, params)
    return _dispatch(op, params)


# --- HTTP server (this process is the single point of failure) --------------


class InvokeHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/invoke":
            self.send_response(404)
            self.end_headers()
            return
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        result = handle(body["op"], body.get("params", {}))
        payload = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        pass  # keep profiling output clean


def run_server(port):
    ThreadingHTTPServer.request_queue_size = 256  # absorb bursty concurrent connects
    httpd = ThreadingHTTPServer(("127.0.0.1", port), InvokeHandler)
    print(f"Traditional (naive monolith) listening on http://127.0.0.1:{port}/invoke")
    httpd.serve_forever()


def run_workload(path):
    events = json.loads(open(path).read())
    for event in events:
        handle(event["op"], event.get("params", {}))
    json.dump(snapshot(), sys.stdout, indent=2, sort_keys=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serve", action="store_true")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--workload", type=str)
    args = parser.parse_args()
    if args.serve:
        run_server(args.port)
    elif args.workload:
        run_workload(args.workload)
    else:
        parser.error("pass --serve or --workload PATH")


if __name__ == "__main__":
    main()
