#!/usr/bin/env bash
# Top-level entry point required by the submission spec: running the
# system, executing test scenarios, and running performance profiling.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

mkdir -p results

echo "== building optional C++ accelerator =="
common/cpp/build.sh

echo "== generating deterministic workload fixture =="
python3 -m common.workload 42 200 common/workload_fixture.json

echo "== running Traditional (in-process, single long-lived interpreter) =="
python3 -m Traditional.server --workload common/workload_fixture.json > results/traditional_final_state.json

echo "== running FaaS (subprocess-per-call, fresh interpreter each time) =="
python3 -c "from FaaS.storage import reset_state; reset_state()"
python3 -m FaaS.gateway --workload common/workload_fixture.json > results/faas_final_state.json

echo "== correctness check: same workload -> same observable state =="
python3 -m common.compare_states results/traditional_final_state.json results/faas_final_state.json

if command -v perf >/dev/null 2>&1; then
    echo "== profiling with perf =="
    profiling/run_perf_traditional.sh common/workload_fixture.json
    profiling/run_perf_faas.sh common/workload_fixture.json
else
    echo "== perf not found on this machine; skipping Part 4 profiling step =="
    echo "   run profiling/run_perf_traditional.sh and profiling/run_perf_faas.sh"
    echo "   on a machine with perf installed (see profiling/ scripts)."
fi
