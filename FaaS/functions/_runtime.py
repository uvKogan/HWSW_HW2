"""
Minimal per-invocation bootstrap shim, analogous to a cloud provider's
Lambda/Functions runtime wrapper. This is invocation plumbing, not
business logic -- the functions in this directory still have zero
dependencies on each other, only on this shared bootstrap and on the
common operation they each wrap.
"""

import json
import os
import sys

from common.operations import OPERATIONS
from FaaS.storage import load_state, save_state, transactional_apply


def _txn_enabled() -> bool:
    return os.environ.get("OLYMPICS_FAAS_TXN", "0") not in ("", "0")


def run(op_name: str) -> None:
    """Entry point for a single stateless invocation: load -> call -> save -> respond.

    Default path uses separate load/save connections (the naive model, which
    the seat-race exploits). With OLYMPICS_FAAS_TXN set, the whole cycle runs
    in one BEGIN IMMEDIATE transaction so concurrent invocations serialise
    correctly -- the FaaS-side fix demonstrated in bench/seat_race.py.
    """
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.loads(sys.stdin.read() or "{}")

    if _txn_enabled():
        result = transactional_apply(op_name, params)
    else:
        state = load_state()
        result = OPERATIONS[op_name](state, params)
        save_state(state)

    json.dump(result, sys.stdout)
