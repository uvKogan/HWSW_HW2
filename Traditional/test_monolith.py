"""
Independent unit tests for the naive monolith (`Traditional/server.py`).

Because the two architectures no longer share a business-logic module, each is
validated on its own: `common/test_operations.py` covers the FaaS core, and
this file covers the monolith. These are single-threaded happy-path + rejection
checks -- the monolith is *functionally correct* sequentially; its problems
(the cross-request _CTX leak, crash-loss, GIL-bound CPU) only surface under
concurrency/crash, which the dedicated benchmarks exercise instead.

Run: `python -m Traditional.test_monolith`  (plain stdlib asserts, no pytest).
"""

from Traditional import server as mono
from common import reference_data as ref

VENUE = ref.VENUES[0]["id"]
VENUE2 = ref.VENUES[1]["id"]
ATHLETE = ref.ATHLETES[0]["id"]
VOLUNTEER = ref.VOLUNTEERS[0]["id"]
COUNTRY = ref.COUNTRIES[0]["code"]
COUNTRY2 = ref.COUNTRIES[1]["code"]
USER = ref.USERS[0]
USER2 = ref.USERS[1]


def test_venue_booking_cycle():
    mono.reset_state()
    assert mono.handle("book_venue_slot", {"venue_id": VENUE, "match_id": "m1"})["ok"]
    assert not mono.handle("book_venue_slot", {"venue_id": VENUE, "match_id": "m2"})["ok"]
    assert mono.handle("release_venue_slot", {"venue_id": VENUE})["ok"]
    assert mono.handle("book_venue_slot", {"venue_id": VENUE, "match_id": "m2"})["ok"]
    assert mono.VENUES[VENUE]["held_by"] == "m2"


def test_unknown_venue_rejected():
    mono.reset_state()
    assert not mono.handle("book_venue_slot", {"venue_id": "atlantis", "match_id": "m1"})["ok"]


def test_seat_sold_once_and_attributed_correctly():
    mono.reset_state()
    assert mono.handle("book_ticket", {"match_id": "m1", "seat_id": "seat1", "user_id": USER})["ok"]
    # same seat to a different user is denied
    assert not mono.handle("book_ticket", {"match_id": "m1", "seat_id": "seat1", "user_id": USER2})["ok"]
    # single-threaded, _CTX is not clobbered, so the seat is attributed correctly
    assert mono.MATCHES["m1"]["seats"]["seat1"] == USER


def test_unknown_user_rejected():
    mono.reset_state()
    assert not mono.handle("book_ticket", {"match_id": "m1", "seat_id": "seat1", "user_id": "nobody"})["ok"]


def test_shuttle_capacity_ceiling():
    mono.reset_state()
    assert mono.handle("dispatch_shuttle", {"shuttle_id": "sh1", "route": "village->x", "seats": 30, "capacity": 40})["ok"]
    assert not mono.handle("dispatch_shuttle", {"shuttle_id": "sh1", "route": "village->x", "seats": 20})["ok"]
    assert mono.SHUTTLES["sh1"]["passengers"] == 30


def test_restaurant_party_size_bounds():
    mono.reset_state()
    assert mono.handle("reserve_restaurant_table", {"athlete_id": ATHLETE, "restaurant_id": "grill", "party_size": 4})["ok"]
    assert not mono.handle("reserve_restaurant_table", {"athlete_id": ATHLETE, "restaurant_id": "grill", "party_size": 99})["ok"]


def test_pubsub_fanout():
    mono.reset_state()
    mono.handle("subscribe_to_updates", {"subscriber_id": USER, "topic": "m1"})
    mono.handle("subscribe_to_updates", {"subscriber_id": USER2, "topic": "m1"})
    mono.handle("subscribe_to_updates", {"subscriber_id": USER, "topic": "m1"})  # idempotent
    assert mono.SUBSCRIPTIONS["m1"] == [USER, USER2]
    res = mono.handle("push_live_event", {"match_id": "m1", "event_type": "score", "details": "1-0"})
    assert res["delivered"] == 2
    assert mono.MATCHES["m1"]["status"] == "score"


def test_country_scoring_and_standings():
    mono.reset_state()
    mono.handle("update_country_score", {"country_code": COUNTRY, "medal": "gold"})
    mono.handle("update_country_score", {"country_code": COUNTRY, "medal": "bronze"})
    mono.handle("update_country_score", {"country_code": COUNTRY2, "medal": "silver"})
    assert mono.SCORES[COUNTRY]["points"] == 3 + 1
    assert not mono.handle("update_country_score", {"country_code": "ZZZ", "medal": "gold"})["ok"]
    mono.handle("recompute_standings", {})
    ranking = mono.STANDINGS["ranking"]
    assert ranking[0]["country"] == COUNTRY and ranking[0]["rank"] == 1  # 4 pts > 2 pts


def test_go_live_cascade():
    mono.reset_state()
    mono.handle("subscribe_to_updates", {"subscriber_id": USER, "topic": "m1"})
    mono.handle("update_country_score", {"country_code": COUNTRY, "medal": "gold"})
    assert mono.handle("go_live", {"match_id": "m1", "stream_id": "str1"})["ok"]
    assert mono.MATCHES["m1"]["status"] == "live"
    assert mono.STREAMS["str1"]["status"] == "on_air"
    assert mono.STANDINGS["ranking"][0]["country"] == COUNTRY


def test_render_highlight_ok_path():
    mono.reset_state()
    # non-corrupt input returns normally (the corrupt path aborts the process,
    # so it is exercised only by bench/fault_isolation.py, never here)
    assert mono.handle("render_highlight", {"match_id": "m1"})["ok"]


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\nOK -- {len(tests)} monolith tests passed")


if __name__ == "__main__":
    main()
