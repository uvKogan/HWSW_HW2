"""
Dispatch layer for the traditional architecture: a single in-memory
state object, mutated directly by the shared operation functions.
No process boundary and no serialization between the "service layer"
and the business logic -- this is the monolith's defining trait.

Concurrency note: `Traditional/server.py` serves requests with a
ThreadingHTTPServer, so concurrent requests mutate the shared `STATE`
from multiple threads. The check-then-write inside `book_ticket` is not
guaranteed atomic across the GIL, so a correct monolith must guard it.
Setting `OLYMPICS_TICKET_LOCK=1` enables that guard -- a single
`threading.Lock` serialising dispatch. This is the whole Traditional-side
fix for the seat-race: one lock, shared memory, done (see
bench/seat_race.py). It is env-gated only so the benchmark can measure
"before" vs. "after"; a real deployment would just always hold it.
"""

import os
import threading

from common.operations import OPERATIONS, initial_state

STATE = initial_state()

_LOCK = threading.Lock()


def _lock_enabled() -> bool:
    return os.environ.get("OLYMPICS_TICKET_LOCK", "0") not in ("", "0")


def dispatch(op_name: str, params: dict) -> dict:
    if op_name not in OPERATIONS:
        return {"ok": False, "message": f"unknown operation {op_name!r}"}
    if _lock_enabled():
        with _LOCK:
            return OPERATIONS[op_name](STATE, params)
    return OPERATIONS[op_name](STATE, params)


def reset_state() -> None:
    global STATE
    STATE = initial_state()
