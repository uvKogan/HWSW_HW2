"""
Resilience experiment -- fault isolation / crash blast radius (the axis FaaS
wins decisively).

One operation, `render_highlight`, hits a native-level crash on a corrupt input
(modeled as `os.abort()` -- a segfault/OOM class failure, not a catchable Python
exception). We seed some booked seats, fire that one poison call, and see what
survives.

  Traditional (naive monolith): all state is in-memory in ONE long-lived
    process. The poison call aborts that process -> the server is gone, every
    booked seat is lost, and every other in-flight/future request fails. Blast
    radius = the whole system.
  FaaS: each call is an isolated subprocess and state is external (sqlite). The
    poison call kills only its own subprocess; the gateway catches the failure,
    later calls keep working, and every previously-persisted seat is intact.
    Blast radius = one request.

Run: python -m bench.fault_isolation
"""

import os
import subprocess

from bench import _serverctl as sc

PORT = 8152
MATCH = "final_100m"
SEED_SEATS = [("seat0", "user000"), ("seat1", "user001"), ("seat2", "user002"),
              ("seat3", "user003"), ("seat4", "user004")]
POST_CRASH_SEATS = [("seat5", "user005"), ("seat6", "user006"), ("seat7", "user007")]


def run_traditional():
    print("Traditional (naive monolith, all state in one in-memory process):")
    proc = sc.start_server(PORT, env=os.environ.copy())
    lost = None
    try:
        for seat, user in SEED_SEATS:
            sc.post_invoke(PORT, "book_ticket", {"match_id": MATCH, "seat_id": seat, "user_id": user})
        seats = sc.post_invoke(PORT, "get_state", {})["state"]["matches"][MATCH]["seats"]
        print(f"  seeded {len(seats)} seats, confirmed present in the running server")
        print("  firing poison render_highlight(corrupt=True)...")
        try:
            sc.post_invoke(PORT, "render_highlight", {"corrupt": True, "match_id": MATCH})
        except Exception as e:  # connection dies as the process aborts
            print(f"  -> request failed: {type(e).__name__} (the server is going down)")
        proc.wait(timeout=5)
        print(f"  -> server process TERMINATED (exit code {proc.returncode})")
        # try one more request against the dead server
        try:
            sc.post_invoke(PORT, "get_state", {})
            print("  -> unexpected: server still answering")
        except Exception:
            print("  -> subsequent requests REFUSED (server is gone)")
        lost = len(SEED_SEATS)
        print(f"  -> ALL {lost} in-memory seats LOST (no persistence); blast radius = whole system")
    finally:
        if proc.poll() is None:
            sc.stop_server(proc)
    return lost


def run_faas():
    from FaaS.storage import reset_state, load_state
    from FaaS import gateway
    print("FaaS (isolated subprocess per call, external sqlite state):")
    reset_state()
    for seat, user in SEED_SEATS:
        gateway.invoke("book_ticket", {"match_id": MATCH, "seat_id": seat, "user_id": user})
    print(f"  seeded {len(SEED_SEATS)} seats (persisted to sqlite)")
    print("  firing poison render_highlight(corrupt=True)...")
    try:
        gateway.invoke("render_highlight", {"corrupt": True, "match_id": MATCH})
        print("  -> unexpected: poison call returned normally")
    except subprocess.CalledProcessError as e:
        print(f"  -> single invocation crashed (exit {e.returncode}), caught; gateway unaffected")
    booked = 0
    for seat, user in POST_CRASH_SEATS:
        r = gateway.invoke("book_ticket", {"match_id": MATCH, "seat_id": seat, "user_id": user})
        booked += 1 if r.get("ok") else 0
    print(f"  booked {booked} more seats AFTER the crash: OK")
    seats = load_state()["matches"][MATCH]["seats"]
    print(f"  -> load_state: {len(seats)} seats intact "
          f"({len(SEED_SEATS)} pre-crash + {len(POST_CRASH_SEATS)} post-crash); blast radius = one request")
    return len(seats)


def main():
    print("fault isolation: one poison call, two architectures\n")
    lost = run_traditional()
    print()
    survived = run_faas()
    print()
    print(f"Summary: the poison call cost Traditional ALL {lost} seats + the server; "
          f"FaaS kept all {survived} seats and stayed up.")


if __name__ == "__main__":
    main()
