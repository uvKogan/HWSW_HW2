#!/usr/bin/env bash
# No CMake dependency on purpose -- this module is one file. Plain
# g++ keeps the build reproducible on any lab machine.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

mkdir -p build
g++ -O2 -Wall -Wextra -std=c++17 accelerator.cpp -o build/accelerator

echo "built common/cpp/build/accelerator"
