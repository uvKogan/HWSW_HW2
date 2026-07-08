"""
Shared business logic for both architectures.

Every operation has the same contract:

    operation(state: dict, params: dict) -> dict (result)

and mutates `state` in place. Both Traditional/services/* and
FaaS/functions/* call the SAME functions here — the only thing that
differs between the two architectures is how `state` is obtained
(persistent in-memory object vs. loaded/saved per call) and how the
call is dispatched (in-process function call vs. subprocess-per-call).

Placeholder names below are generic across the guide's example
scenarios (hospital / hotel / airport / university). Once a scenario
is picked, rename these 7 to match it one-for-one — keep the
(state, params) -> result signature so nothing else has to change.
"""

from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log(state: dict, event: str, **fields) -> None:
    state.setdefault("log", []).append({"ts": _now(), "event": event, **fields})


def schedule_resource(state: dict, params: dict) -> dict:
    """Reserve a shared resource (OR / hotel room / gate / classroom) for an entity."""
    resource_id = params["resource_id"]
    entity_id = params["entity_id"]
    resources = state.setdefault("resources", {})
    resource = resources.setdefault(resource_id, {"status": "free", "held_by": None})

    if resource["status"] != "free":
        _log(state, "schedule_resource_denied", resource_id=resource_id, entity_id=entity_id)
        return {"ok": False, "message": f"resource {resource_id} not free"}

    resource["status"] = "occupied"
    resource["held_by"] = entity_id
    _log(state, "schedule_resource", resource_id=resource_id, entity_id=entity_id)
    return {"ok": True, "message": f"resource {resource_id} assigned to {entity_id}"}


def release_resource(state: dict, params: dict) -> dict:
    """Release a previously scheduled resource back to the free pool."""
    resource_id = params["resource_id"]
    resources = state.setdefault("resources", {})
    resource = resources.get(resource_id)

    if resource is None or resource["status"] == "free":
        _log(state, "release_resource_noop", resource_id=resource_id)
        return {"ok": False, "message": f"resource {resource_id} was not occupied"}

    resource["status"] = "free"
    resource["held_by"] = None
    _log(state, "release_resource", resource_id=resource_id)
    return {"ok": True, "message": f"resource {resource_id} released"}


def assign_staff(state: dict, params: dict) -> dict:
    """Assign a staff member (nurse / agent / TA / ...) to a unit/department."""
    staff_id = params["staff_id"]
    unit = params["unit"]
    staff = state.setdefault("staff", {})
    entry = staff.setdefault(staff_id, {"unit": None, "shift": None})
    entry["unit"] = unit
    _log(state, "assign_staff", staff_id=staff_id, unit=unit)
    return {"ok": True, "message": f"staff {staff_id} assigned to {unit}"}


def update_shift(state: dict, params: dict) -> dict:
    """Update a staff member's shift assignment."""
    staff_id = params["staff_id"]
    shift = params["shift"]
    staff = state.setdefault("staff", {})
    entry = staff.setdefault(staff_id, {"unit": None, "shift": None})
    entry["shift"] = shift
    _log(state, "update_shift", staff_id=staff_id, shift=shift)
    return {"ok": True, "message": f"staff {staff_id} shift set to {shift}"}


def handle_capacity_event(state: dict, params: dict) -> dict:
    """Adjust current load against a hard capacity ceiling (ER beds / rooms / gates / seats)."""
    delta = params["delta"]
    capacity = state.setdefault("capacity", {"current": 0, "max": params.get("max", 100)})
    new_value = capacity["current"] + delta

    if new_value < 0 or new_value > capacity["max"]:
        _log(state, "capacity_rejected", delta=delta, current=capacity["current"])
        return {"ok": False, "message": "capacity change rejected", "current": capacity["current"]}

    capacity["current"] = new_value
    _log(state, "capacity_changed", delta=delta, current=new_value)
    return {"ok": True, "message": "capacity updated", "current": new_value}


def track_entity_status(state: dict, params: dict) -> dict:
    """Track lifecycle status of a tracked entity (patient / guest / flight / student)."""
    entity_id = params["entity_id"]
    status = params["status"]
    entities = state.setdefault("entities", {})
    entities[entity_id] = {"status": status, "updated_at": _now()}
    _log(state, "track_entity_status", entity_id=entity_id, status=status)
    return {"ok": True, "message": f"entity {entity_id} status set to {status}"}


def allocate_equipment(state: dict, params: dict) -> dict:
    """Allocate a piece of equipment to a target (bed / room / gate / lab)."""
    equipment_id = params["equipment_id"]
    target = params["target"]
    equipment = state.setdefault("equipment", {})
    equipment[equipment_id] = {"assigned_to": target, "updated_at": _now()}
    _log(state, "allocate_equipment", equipment_id=equipment_id, target=target)
    return {"ok": True, "message": f"equipment {equipment_id} allocated to {target}"}


# Registry used by both architectures' dispatch layers.
OPERATIONS = {
    "schedule_resource": schedule_resource,
    "release_resource": release_resource,
    "assign_staff": assign_staff,
    "update_shift": update_shift,
    "handle_capacity_event": handle_capacity_event,
    "track_entity_status": track_entity_status,
    "allocate_equipment": allocate_equipment,
}


def initial_state() -> dict:
    return {"resources": {}, "staff": {}, "capacity": {"current": 0, "max": 100}, "entities": {}, "equipment": {}, "log": []}
