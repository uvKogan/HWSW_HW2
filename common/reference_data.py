"""
Static reference ("master") data for the Olympic Games Management System.

This is the fixed roster the system operates over: the countries, athletes,
volunteers, venues, and spectator user IDs that exist in the world. It is
deliberately *separate* from the mutable `state` dict in
`common.operations`: reference data is read-only master data (rarely
changes), whereas `state` is the transactional data mutated by operations
(bookings, scores, subscriptions, ...). Both architectures import this
module identically -- it is shared, like `common.operations`, so Traditional
and FaaS validate against exactly the same roster.

Operations that take an entity ID validate it against the derived lookup
sets below (e.g. `COUNTRY_CODES`, `ATHLETE_IDS`) and reject unknown IDs, and
`common.workload` draws its random IDs from these pools so a replayed
workload looks like a real, bounded Games roster rather than unbounded
synthetic IDs.

Everything here is JSON-clean (plain strings/ints in lists and dicts) so it
survives the FaaS sqlite round-trip identically to Traditional's in-memory
copy.
"""

# --- Countries (National Olympic Committees) -------------------------------

COUNTRIES = [
    {"code": "USA", "name": "United States"},
    {"code": "FRA", "name": "France"},
    {"code": "GBR", "name": "Great Britain"},
    {"code": "JPN", "name": "Japan"},
    {"code": "GER", "name": "Germany"},
    {"code": "AUS", "name": "Australia"},
    {"code": "CAN", "name": "Canada"},
    {"code": "CHN", "name": "China"},
    {"code": "BRA", "name": "Brazil"},
    {"code": "ITA", "name": "Italy"},
]

# --- Sports contested (used to tag athletes) -------------------------------

SPORTS = [
    "Athletics", "Swimming", "Gymnastics", "Basketball", "Cycling",
    "Judo", "Rowing", "Tennis", "Boxing", "Volleyball",
]

# --- Athletes --------------------------------------------------------------
# ~30 athletes, each tied to a country code above and a sport above.

ATHLETES = [
    {"id": "ath001", "name": "James Carter",     "country": "USA", "sport": "Athletics"},
    {"id": "ath002", "name": "Emma Sullivan",    "country": "USA", "sport": "Swimming"},
    {"id": "ath003", "name": "Michael Reed",     "country": "USA", "sport": "Basketball"},
    {"id": "ath004", "name": "Chloe Bennett",    "country": "GBR", "sport": "Cycling"},
    {"id": "ath005", "name": "Oliver Hughes",    "country": "GBR", "sport": "Rowing"},
    {"id": "ath006", "name": "Sophie Clarke",    "country": "GBR", "sport": "Athletics"},
    {"id": "ath007", "name": "Louis Moreau",     "country": "FRA", "sport": "Judo"},
    {"id": "ath008", "name": "Camille Dubois",   "country": "FRA", "sport": "Gymnastics"},
    {"id": "ath009", "name": "Hugo Laurent",     "country": "FRA", "sport": "Swimming"},
    {"id": "ath010", "name": "Yuki Tanaka",      "country": "JPN", "sport": "Judo"},
    {"id": "ath011", "name": "Haruto Sato",      "country": "JPN", "sport": "Gymnastics"},
    {"id": "ath012", "name": "Aoi Yamamoto",     "country": "JPN", "sport": "Swimming"},
    {"id": "ath013", "name": "Lena Schmidt",     "country": "GER", "sport": "Athletics"},
    {"id": "ath014", "name": "Felix Wagner",     "country": "GER", "sport": "Cycling"},
    {"id": "ath015", "name": "Mia Becker",       "country": "GER", "sport": "Rowing"},
    {"id": "ath016", "name": "Jack Wilson",      "country": "AUS", "sport": "Swimming"},
    {"id": "ath017", "name": "Olivia Harris",    "country": "AUS", "sport": "Tennis"},
    {"id": "ath018", "name": "Noah Campbell",    "country": "AUS", "sport": "Volleyball"},
    {"id": "ath019", "name": "Liam Tremblay",    "country": "CAN", "sport": "Boxing"},
    {"id": "ath020", "name": "Ava Gagnon",       "country": "CAN", "sport": "Athletics"},
    {"id": "ath021", "name": "Ethan Roy",        "country": "CAN", "sport": "Basketball"},
    {"id": "ath022", "name": "Wei Zhang",        "country": "CHN", "sport": "Gymnastics"},
    {"id": "ath023", "name": "Lin Chen",         "country": "CHN", "sport": "Swimming"},
    {"id": "ath024", "name": "Fang Liu",         "country": "CHN", "sport": "Volleyball"},
    {"id": "ath025", "name": "Lucas Silva",      "country": "BRA", "sport": "Volleyball"},
    {"id": "ath026", "name": "Beatriz Souza",    "country": "BRA", "sport": "Judo"},
    {"id": "ath027", "name": "Gabriel Costa",    "country": "BRA", "sport": "Boxing"},
    {"id": "ath028", "name": "Marco Rossi",      "country": "ITA", "sport": "Cycling"},
    {"id": "ath029", "name": "Giulia Ricci",     "country": "ITA", "sport": "Tennis"},
    {"id": "ath030", "name": "Matteo Conti",     "country": "ITA", "sport": "Rowing"},
]

# --- Volunteers ------------------------------------------------------------
# ~15 volunteers, assignable to venues by the assign_volunteer operation.

VOLUNTEERS = [
    {"id": "vol001", "name": "Ana Martinez"},
    {"id": "vol002", "name": "Ben Cohen"},
    {"id": "vol003", "name": "Carla Nguyen"},
    {"id": "vol004", "name": "David Park"},
    {"id": "vol005", "name": "Elena Petrova"},
    {"id": "vol006", "name": "Frank O'Brien"},
    {"id": "vol007", "name": "Grace Kim"},
    {"id": "vol008", "name": "Hassan Ali"},
    {"id": "vol009", "name": "Ines Fernandez"},
    {"id": "vol010", "name": "Jonas Weber"},
    {"id": "vol011", "name": "Kavya Rao"},
    {"id": "vol012", "name": "Leo Marchetti"},
    {"id": "vol013", "name": "Maya Goldberg"},
    {"id": "vol014", "name": "Nate Foster"},
    {"id": "vol015", "name": "Olga Ivanova"},
]

# --- Venues ----------------------------------------------------------------
# Real Los Angeles venues slated for the LA 2028 Summer Games, used purely as
# realistic fixture data (not a claim about the actual competition schedule).

VENUES = [
    {"id": "sofi_stadium",     "name": "SoFi Stadium"},
    {"id": "intuit_dome",      "name": "Intuit Dome"},
    {"id": "crypto_arena",     "name": "Crypto.com Arena"},
    {"id": "the_forum",        "name": "Kia Forum"},
    {"id": "peacock_theater",  "name": "Peacock Theater"},
    {"id": "bmo_stadium",      "name": "BMO Stadium"},
    {"id": "dodger_stadium",   "name": "Dodger Stadium"},
    {"id": "la_coliseum",      "name": "Los Angeles Memorial Coliseum"},
    {"id": "rose_bowl",        "name": "Rose Bowl"},
    {"id": "honda_center",     "name": "Honda Center"},
    {"id": "galen_center",     "name": "Galen Center"},
    {"id": "long_beach_arena", "name": "Long Beach Arena"},
]

# --- Spectator users -------------------------------------------------------
# Synthetic on purpose: 200 anonymous spectator/subscriber IDs, the pool the
# ticketing (book_ticket) and pub/sub (subscribe_to_updates) operations draw
# from and that the concurrency benchmark uses as simulated concurrent users.

USERS = [f"user{n:03d}" for n in range(200)]

# --- Derived lookup sets (O(1) validation) ---------------------------------
# Operations validate entity IDs against these; kept as frozensets so they're
# cheap to check and obviously read-only.

COUNTRY_CODES = frozenset(c["code"] for c in COUNTRIES)
ATHLETE_IDS = frozenset(a["id"] for a in ATHLETES)
VOLUNTEER_IDS = frozenset(v["id"] for v in VOLUNTEERS)
VENUE_IDS = frozenset(v["id"] for v in VENUES)
USER_IDS = frozenset(USERS)


def summary() -> dict:
    """Small helper for sanity checks / debugging: counts of each pool."""
    return {
        "countries": len(COUNTRIES),
        "sports": len(SPORTS),
        "athletes": len(ATHLETES),
        "volunteers": len(VOLUNTEERS),
        "venues": len(VENUES),
        "users": len(USERS),
    }


if __name__ == "__main__":
    import json
    # Cheap self-check: every athlete's country must be a real NOC code.
    bad = [a["id"] for a in ATHLETES if a["country"] not in COUNTRY_CODES]
    assert not bad, f"athletes reference unknown country codes: {bad}"
    assert len(ATHLETE_IDS) == len(ATHLETES), "duplicate athlete IDs"
    assert len(VENUE_IDS) == len(VENUES), "duplicate venue IDs"
    print(json.dumps(summary(), indent=2))
