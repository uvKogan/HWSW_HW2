#!/usr/bin/env bash
# perf stat + perf record over the Traditional in-process workload run.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

WORKLOAD="${1:-common/workload_fixture.json}"
OUT="results/traditional"
mkdir -p "$OUT"

if ! command -v perf >/dev/null 2>&1; then
    echo "perf not found on this machine -- run this on the lab/profiling machine." >&2
    exit 1
fi

perf stat -d -o "$OUT/perf_stat.txt" -- \
    python3 -m Traditional.server --workload "$WORKLOAD" > "$OUT/final_state.json"

perf record -F 99 -g -o "$OUT/perf.data" -- \
    python3 -m Traditional.server --workload "$WORKLOAD" > /dev/null

echo "wrote $OUT/perf_stat.txt, $OUT/perf.data, $OUT/final_state.json"
