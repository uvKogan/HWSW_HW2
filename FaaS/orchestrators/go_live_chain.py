"""
Idiomatic FaaS decomposition of the go_live cascade (Part 3 evidence).

The Traditional architecture runs `go_live` as ONE atomic in-process
function call (see common/operations.py). The *naive* FaaS port
(FaaS/functions/go_live.py) technically works but cheats: it bundles all
three business steps behind a single load->call->save, which quietly
violates the FaaS principle of independent, isolated functions with minimal
inter-dependencies.

This orchestrator does what a FaaS design *should*: chain three independent,
separately-deployable function invocations. The cost of that honesty is the
whole point of Part 3 -- three separate subprocess spawns and three separate
sqlite load/save round-trips, with NO transaction spanning them:

    push_live_event   -> spawn, load, mutate, save
    (crash here?) -----> match is announced + subscribers notified,
                         stream not yet on air, standings still stale
    allocate_stream   -> spawn, load, mutate, save
    (crash here?) -----> match live + streaming, but standings stale
    recompute_standings -> spawn, load, mutate, save

A failure between steps leaves a partially-applied cascade -- a state the
Traditional single call can never land in. Extending the system with this
feature therefore touches more moving parts and is riskier in FaaS: the
atomicity Traditional gets for free must be rebuilt (sagas / compensation /
idempotency) or accepted as a consistency hole.

Usage (same result as the naive op, but via three real invocations):
    python -m FaaS.orchestrators.go_live_chain '{"match_id": "match3", "venue_id": "sofi_stadium", "stream_id": "stream1"}'
"""

import json
import sys

from FaaS.gateway import invoke


def go_live_chain(match_id: str, venue_id: str, stream_id: str) -> dict:
    steps = []
    steps.append(("push_live_event", invoke(
        "push_live_event",
        {"match_id": match_id, "event_type": "live", "details": "match is live"},
    )))
    # --- partial-failure boundary: a crash here leaves the match announced
    #     and subscribers notified, but no stream and stale standings. ---
    steps.append(("allocate_stream", invoke(
        "allocate_stream", {"stream_id": stream_id, "match_id": match_id},
    )))
    steps.append(("recompute_standings", invoke("recompute_standings", {})))

    return {
        "ok": all(r.get("ok") for _, r in steps),
        "match_id": match_id,
        "steps": [name for name, _ in steps],
    }


def main() -> None:
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.loads(sys.stdin.read() or "{}")
    print(json.dumps(go_live_chain(params["match_id"], params["venue_id"], params["stream_id"])))


if __name__ == "__main__":
    main()
