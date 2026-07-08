"""
FaaS architecture entry point: simulates the platform's event
router/API gateway. Each event in the workload becomes an independent
process invocation -- a fresh Python interpreter, no shared memory
with the previous call, state read from and written back to external
storage (FaaS/storage.py).

Usage:
    python3 -m FaaS.gateway --workload path/to/events.json

perf note: `perf stat`/`perf record` follow forked children by
default, so wrapping this whole command is enough to capture the
aggregate cost across every spawned function process -- no need to
loop perf itself.
"""

import argparse
import json
import subprocess
import sys

from FaaS.storage import load_state


def invoke(op_name: str, params: dict) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", f"FaaS.functions.{op_name}", json.dumps(params)],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)


def run_workload(path: str) -> None:
    events = json.loads(open(path).read())
    for event in events:
        invoke(event["op"], event["params"])
    json.dump(load_state(), sys.stdout, indent=2, sort_keys=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workload", type=str, required=True)
    args = parser.parse_args()
    run_workload(args.workload)


if __name__ == "__main__":
    main()
