"""
Sanity tests for the pure business logic in `common.operations`.

Why this exists: `common.compare_states` only checks that Traditional and FaaS
agree on the final state after a replay. Traditional and FaaS are independent
implementations (Traditional has its own business logic; only FaaS runs this
module), so that agreement is evidence the two sides match, not proof either
one is *correct*. These tests are what actually verifies this module's ops
are correct.

Run: `python -m common.test_operations`  (plain stdlib asserts, no pytest).
"""

from common.operations import OPERATIONS, initial_state
from common import reference_data as ref

VENUE = ref.VENUES[0]["id"]
ATHLETE = ref.ATHLETES[0]["id"]
VOLUNTEER = ref.VOLUNTEERS[0]["id"]
COUNTRY = ref.COUNTRIES[0]["code"]
USER = ref.USERS[0]


def op(name, state, **params):
    return OPERATIONS[name](state, params)


def test_venue_booking_cycle():
    s = initial_state()
    assert op("book_venue_slot", s, venue_id=VENUE, match_id="m1")["ok"]
    # double-book denied
    assert not op("book_venue_slot", s, venue_id=VENUE, match_id="m2")["ok"]
    # release then re-book allowed
    assert op("release_venue_slot", s, venue_id=VENUE)["ok"]
    assert op("book_venue_slot", s, venue_id=VENUE, match_id="m2")["ok"]
    assert s["venues"][VENUE]["held_by"] == "m2"


def test_unknown_venue_rejected():
    s = initial_state()
    assert not op("book_venue_slot", s, venue_id="atlantis", match_id="m1")["ok"]


def test_seat_sold_once():
    s = initial_state()
    assert op("book_ticket", s, match_id="m1", seat_id="seat1", user_id=USER)["ok"]
    # same seat to a different user is denied (the race the benchmark stresses)
    other = ref.USERS[1]
    assert not op("book_ticket", s, match_id="m1", seat_id="seat1", user_id=other)["ok"]
    assert s["matches"]["m1"]["seats"]["seat1"] == USER


def test_unknown_user_rejected():
    s = initial_state()
    assert not op("book_ticket", s, match_id="m1", seat_id="seat1", user_id="nobody")["ok"]


def test_shuttle_capacity_ceiling():
    s = initial_state()
    assert op("dispatch_shuttle", s, shuttle_id="sh1", route="village->x", seats=30, capacity=40)["ok"]
    # boarding beyond capacity denied; load unchanged
    assert not op("dispatch_shuttle", s, shuttle_id="sh1", route="village->x", seats=20)["ok"]
    assert s["shuttles"]["sh1"]["passengers"] == 30


def test_restaurant_party_size_bounds():
    s = initial_state()
    assert op("reserve_restaurant_table", s, athlete_id=ATHLETE, restaurant_id="grill", party_size=4)["ok"]
    assert not op("reserve_restaurant_table", s, athlete_id=ATHLETE, restaurant_id="grill", party_size=99)["ok"]


def test_pubsub_fanout():
    s = initial_state()
    a, b = ref.USERS[0], ref.USERS[1]
    op("subscribe_to_updates", s, subscriber_id=a, topic="m1")
    op("subscribe_to_updates", s, subscriber_id=b, topic="m1")
    op("subscribe_to_updates", s, subscriber_id=a, topic="m1")  # idempotent
    assert s["subscriptions"]["m1"] == [a, b]
    res = op("push_live_event", s, match_id="m1", event_type="score", details="1-0")
    assert res["delivered"] == 2
    assert s["matches"]["m1"]["status"] == "score"


def test_country_scoring_points():
    s = initial_state()
    op("update_country_score", s, country_code=COUNTRY, medal="gold")
    op("update_country_score", s, country_code=COUNTRY, medal="bronze")
    entry = s["country_scores"][COUNTRY]
    assert entry["gold"] == 1 and entry["bronze"] == 1
    assert entry["points"] == 3 + 1
    assert not op("update_country_score", s, country_code="ZZZ", medal="gold")["ok"]


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\nOK -- {len(tests)} operation tests passed")


if __name__ == "__main__":
    main()
