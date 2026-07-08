#!/usr/bin/env bash
# perf stat + perf record over the FaaS gateway. perf follows forked
# children by default, so this aggregates metrics across every
# spawned function process automatically -- no manual looping needed.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

WORKLOAD="${1:-common/workload_fixture.json}"
OUT="results/faas"
mkdir -p "$OUT"

if ! command -v perf >/dev/null 2>&1; then
    echo "perf not found on this machine -- run this on the lab/profiling machine." >&2
    exit 1
fi

python3 -c "from FaaS.storage import reset_state; reset_state()"
perf stat -d -o "$OUT/perf_stat.txt" -- \
    python3 -m FaaS.gateway --workload "$WORKLOAD" > "$OUT/final_state.json"

python3 -c "from FaaS.storage import reset_state; reset_state()"
perf record -F 99 -g -o "$OUT/perf.data" -- \
    python3 -m FaaS.gateway --workload "$WORKLOAD" > /dev/null

echo "wrote $OUT/perf_stat.txt, $OUT/perf.data, $OUT/final_state.json"
