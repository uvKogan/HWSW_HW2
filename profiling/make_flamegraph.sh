#!/usr/bin/env bash
# Turns a perf.data file (produced by run_perf_traditional.sh /
# run_perf_faas.sh) into an SVG flamegraph. Requires
# profiling/flamegraph/fetch.sh to have been run once.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PERF_DATA="$1"          # e.g. results/traditional/perf.data
OUT_SVG="$2"            # e.g. results/traditional/flamegraph.svg
FG=profiling/flamegraph/FlameGraph

if [ ! -d "$FG" ]; then
    echo "run profiling/flamegraph/fetch.sh first" >&2
    exit 1
fi

perf script -i "$PERF_DATA" | "$FG/stackcollapse-perf.pl" | "$FG/flamegraph.pl" > "$OUT_SVG"
echo "wrote $OUT_SVG"
