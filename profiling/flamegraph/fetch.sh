#!/usr/bin/env bash
# One-time fetch of Brendan Gregg's FlameGraph scripts (not vendored
# in-repo -- it's a large external tool, see HW1 for the same setup).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

if [ -d FlameGraph ]; then
    echo "FlameGraph already present."
    exit 0
fi

git clone --depth 1 https://github.com/brendangregg/FlameGraph.git
