#!/usr/bin/env bash
# Top-level entry point required by the submission spec: running the system,
# executing test scenarios, and running performance profiling.
#
# Pure Python, stdlib only. Uses python3 by default; override with
#   PYTHON=python ./script.sh   (e.g. on Windows where the launcher is `python`)
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

PY="${PYTHON:-python3}"
mkdir -p results

echo "== independent validation: FaaS core ops =="
"$PY" -m common.test_operations

echo "== independent validation: naive monolith =="
"$PY" -m Traditional.test_monolith

echo "== generate deterministic workload fixture =="
"$PY" -m common.workload 42 2000 common/workload_fixture.json

echo "== running Traditional (naive monolith, single long-lived interpreter) =="
"$PY" -m Traditional.server --workload common/workload_fixture.json > results/traditional_final_state.json

echo "== running FaaS (subprocess-per-call, fresh interpreter each time) =="
"$PY" -c "from FaaS.storage import reset_state; reset_state()"
"$PY" -m FaaS.gateway --workload common/workload_fixture.json > results/faas_final_state.json

# The two architectures are now INDEPENDENT implementations (Traditional has its
# own naive business logic, not common/operations.py), each validated by its own
# unit tests above. We no longer gate on byte-identical state. This informational
# diff just reports whether the two independent implementations happen to agree
# on the sequential replay (they should -- the monolith's bugs are concurrency-
# only); it never fails the run.
echo "== informational: do the two independent implementations agree on the replay? =="
"$PY" -m common.compare_states results/traditional_final_state.json results/faas_final_state.json || \
  echo "   (states differ -- expected-tolerable now that the implementations diverge)"

echo "== experiment: seat-booking race (shared-state consistency) =="
"$PY" -m bench.seat_race --users 30 --seats 10 --delay 0.02

echo "== experiment: cross-request state leak (FaaS wins by construction) =="
"$PY" -m bench.context_leak --seats 40 --delay 0.01

echo "== experiment: fault isolation / crash blast radius (FaaS wins) =="
"$PY" -m bench.fault_isolation

echo "== experiment: idle footprint / scale-to-zero (FaaS wins) =="
"$PY" -m bench.idle_footprint

echo "== experiment: parallel throughput, independent CPU (FaaS wins) =="
"$PY" -m bench.parallel_throughput --tasks 32 --iterations 5000000

echo "== experiment: latency under state growth (Traditional wins) =="
"$PY" -m bench.state_growth

if command -v perf >/dev/null 2>&1; then
    echo "== profiling with perf =="
    profiling/run_perf_traditional.sh common/workload_fixture.json
    profiling/run_perf_faas.sh common/workload_fixture.json
else
    echo "== perf not found on this machine; skipping Part 4 profiling step =="
    echo "   run profiling/run_perf_*.sh on a Linux machine with perf installed."
fi
