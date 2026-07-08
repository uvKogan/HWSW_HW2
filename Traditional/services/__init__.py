"""
Dispatch layer for the traditional architecture: a single in-memory
state object, mutated directly by the shared operation functions.
No process boundary and no serialization between the "service layer"
and the business logic -- this is the monolith's defining trait.
"""

from common.operations import OPERATIONS, initial_state

STATE = initial_state()


def dispatch(op_name: str, params: dict) -> dict:
    if op_name not in OPERATIONS:
        return {"ok": False, "message": f"unknown operation {op_name!r}"}
    return OPERATIONS[op_name](STATE, params)


def reset_state() -> None:
    global STATE
    STATE = initial_state()
