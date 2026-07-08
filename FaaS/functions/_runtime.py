"""
Minimal per-invocation bootstrap shim, analogous to a cloud provider's
Lambda/Functions runtime wrapper. This is invocation plumbing, not
business logic -- the functions in this directory still have zero
dependencies on each other, only on this shared bootstrap and on the
common operation they each wrap.
"""

import json
import sys

from common.operations import OPERATIONS
from FaaS.storage import load_state, save_state


def run(op_name: str) -> None:
    """Entry point for a single stateless invocation: load -> call -> save -> respond."""
    params = json.loads(sys.argv[1]) if len(sys.argv) > 1 else json.loads(sys.stdin.read() or "{}")

    state = load_state()
    result = OPERATIONS[op_name](state, params)
    save_state(state)

    json.dump(result, sys.stdout)
