"""
Correctness gate: diff the final states produced by the Traditional
and FaaS runs after replaying the same workload. Wall-clock fields
(`log`, `updated_at`) will always differ between runs since the two
architectures execute at different real times, so they're excluded
from the comparison -- everything else must match exactly.
"""

import json
import sys

_VOLATILE_KEYS = {"log", "updated_at", "ts"}


def _strip_volatile(value):
    if isinstance(value, dict):
        return {k: _strip_volatile(v) for k, v in value.items() if k not in _VOLATILE_KEYS}
    if isinstance(value, list):
        return [_strip_volatile(v) for v in value]
    return value


def main() -> None:
    path_a, path_b = sys.argv[1], sys.argv[2]
    state_a = _strip_volatile(json.loads(open(path_a).read()))
    state_b = _strip_volatile(json.loads(open(path_b).read()))

    if state_a == state_b:
        print("MATCH: both architectures produced identical final state")
        sys.exit(0)

    print("DIFF: final states differ")
    print(f"--- {path_a}\n{json.dumps(state_a, indent=2, sort_keys=True)}")
    print(f"--- {path_b}\n{json.dumps(state_b, indent=2, sort_keys=True)}")
    sys.exit(1)


if __name__ == "__main__":
    main()
