"""
Deterministic workload generator shared by both architectures.

Both Traditional/server.py and FaaS/gateway.py replay the exact same
event sequence, so Part 4's performance comparison is driven by
identical work, and the final states can be diffed for a correctness
check (same inputs -> same observable outputs, regardless of
execution architecture).
"""

import json
import random
import sys
from pathlib import Path

from common.operations import OPERATIONS

N_RESOURCES = 10
N_STAFF = 6
N_ENTITIES = 20
N_EQUIPMENT = 8


def generate_workload(seed: int = 42, n_events: int = 200) -> list[dict]:
    rng = random.Random(seed)
    op_names = list(OPERATIONS.keys())
    events = []

    for _ in range(n_events):
        op = rng.choice(op_names)

        if op == "schedule_resource":
            params = {"resource_id": f"res{rng.randrange(N_RESOURCES)}", "entity_id": f"ent{rng.randrange(N_ENTITIES)}"}
        elif op == "release_resource":
            params = {"resource_id": f"res{rng.randrange(N_RESOURCES)}"}
        elif op == "assign_staff":
            params = {"staff_id": f"staff{rng.randrange(N_STAFF)}", "unit": rng.choice(["A", "B", "C"])}
        elif op == "update_shift":
            params = {"staff_id": f"staff{rng.randrange(N_STAFF)}", "shift": rng.choice(["day", "night"])}
        elif op == "handle_capacity_event":
            params = {"delta": rng.choice([-5, -1, 1, 5])}
        elif op == "track_entity_status":
            params = {"entity_id": f"ent{rng.randrange(N_ENTITIES)}", "status": rng.choice(["pending", "active", "closed"])}
        elif op == "allocate_equipment":
            params = {"equipment_id": f"eq{rng.randrange(N_EQUIPMENT)}", "target": f"res{rng.randrange(N_RESOURCES)}"}
        else:
            raise ValueError(f"no param generator wired up for operation {op!r}")

        events.append({"op": op, "params": params})

    return events


def main() -> None:
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    n_events = int(sys.argv[2]) if len(sys.argv) > 2 else 200
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("common/workload_fixture.json")

    events = generate_workload(seed=seed, n_events=n_events)
    out_path.write_text(json.dumps(events, indent=2))
    print(f"wrote {len(events)} events to {out_path}")


if __name__ == "__main__":
    main()
