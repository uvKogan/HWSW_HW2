#!/usr/bin/env bash
# make_submission.sh — assemble HW2.zip for the course staff.
#
# Rebuilds the report PDFs (injecting the real student IDs from the gitignored
# report/ids.local so they never live in the repo) and stages the required +
# supporting files into submission/, then zips them.
#
# Requires: typst (override with TYPST=..., e.g. TYPST=~/bin/typst) and zip.
# Best run on the Linux box; the system code itself is pure Python and
# OS-agnostic.
set -euo pipefail

REPO="$(cd "$(dirname "$0")" && pwd)"
OUT="${REPO}/submission"
ZIP="${REPO}/HW2.zip"
TYPST="${TYPST:-typst}"

# ── 1. IDs — injected at compile time, never stored in the repo ──────────────
IDS="${REPO}/report/ids.local"
if [[ -f "${IDS}" ]]; then
  # shellcheck source=/dev/null
  source "${IDS}"
else
  echo "WARNING: ${IDS} not found — PDFs will show <ID> placeholders." >&2
fi
ID_INPUTS=(--input "matan-id=${MATAN_ID:-<ID>}" --input "yuval-id=${YUVAL_ID:-<ID>}")

# ── 2. (Re)build the PDFs ────────────────────────────────────────────────────
"${TYPST}" compile "${REPO}/report/report.typ" "${REPO}/report/report.pdf"
"${TYPST}" compile "${ID_INPUTS[@]}" "${REPO}/report/ids.typ" "${REPO}/report/ids.pdf"

# ── 3. Stage the files ───────────────────────────────────────────────────────
rm -rf "${OUT}" "${ZIP}"
mkdir -p "${OUT}/report"

# Required by the brief.
cp "${REPO}/report/report.pdf" "${OUT}/"        # ≤6-page written analysis
cp "${REPO}/report/ids.pdf"    "${OUT}/"        # names + IDs
cp "${REPO}/script.sh"         "${OUT}/"        # run / test / profile
cp -r "${REPO}/Traditional"    "${OUT}/"        # traditional architecture
cp -r "${REPO}/FaaS"           "${OUT}/"        # FaaS architecture

# Optional — needed for the code to actually run: both architectures import the
# shared core, and script.sh drives the benchmarks + profiling wrappers.
cp -r "${REPO}/common"    "${OUT}/"
cp -r "${REPO}/bench"     "${OUT}/"
cp -r "${REPO}/profiling" "${OUT}/"

# Supporting evidence the report cites / the course requires.
cp "${REPO}/README.md"         "${OUT}/"        # how to run
cp "${REPO}/prompts.md"        "${OUT}/"        # AI-usage disclosure (required)
cp "${REPO}/report/results.md" "${OUT}/report/" # measured Part 4 numbers

# ── 4. Strip build cruft that cp -r may have pulled in ───────────────────────
find "${OUT}" -type d -name __pycache__ -prune -exec rm -rf {} +
find "${OUT}" -type f \( -name '*.pyc' -o -name '*.db' -o -name 'workload_fixture.json' \) -delete
rm -rf "${OUT}/FaaS/functions/data"

# ── 5. Zip ───────────────────────────────────────────────────────────────────
( cd "${OUT}" && zip -r -q "${ZIP}" . )
echo "Built ${ZIP}"
( cd "${OUT}" && find . -type f | sort )
echo "--- size ---"; du -h "${ZIP}" | cut -f1
