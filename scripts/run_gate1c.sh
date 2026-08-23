#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate1c"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate1c-$RUN_ID"}
mkdir -p "$REPORT_DIR"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate1c.sh"
python3 "$ROOT/scripts/generate_gate1c_cases.py" "$RUN_DIR"

for case_name in continuum hybrid reference; do
    blockMesh -case "$RUN_DIR/$case_name" \
        > "$REPORT_DIR/gate1c-blockMesh-$case_name.log" 2>&1
done
for case_name in hybrid reference; do
    dsmcInitialise -case "$RUN_DIR/$case_name" \
        > "$REPORT_DIR/gate1c-dsmcInitialise-$case_name.log" 2>&1
done

CONTINUUM_LOG="$REPORT_DIR/gate1c_continuum.log"
printf 'GATE1C_CONTINUUM_RUN_ORDER=1\n'
timeout --signal=TERM 900 \
    rhoCentralFoam -case "$RUN_DIR/continuum" \
    2>&1 | tee "$CONTINUUM_LOG"

# The publisher must read the converged snapshot, not the initial fields.
foamDictionary \
    -entry startFrom \
    -set latestTime \
    "$RUN_DIR/continuum/system/controlDict"

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 1C runner.\n' >&2
    exit 127
fi

HYBRID_LOG="$REPORT_DIR/gate1c_hybrid.log"
printf 'GATE1C_HYBRID_RUN_ORDER=2\n'
timeout --signal=TERM 900 \
    "$MPI_LAUNCHER" \
    -np 1 "$BUILD_DIR/openfoam/muiContinuumPublisher" \
        -case "$RUN_DIR/continuum" \
    : \
    -np 1 env GATE1C_ROLE=hybrid \
        "$BUILD_DIR/openfoam/dsmcFoamGate1C" \
        -case "$RUN_DIR/hybrid" \
    2>&1 | tee "$HYBRID_LOG"

grep -q 'GATE1C_PASS role=publisher' "$HYBRID_LOG"
grep -q 'GATE1C_PASS role=hybrid' "$HYBRID_LOG"

# Deliberately run the full DSMC reference only after the interface has been
# fixed and the hybrid result has completed.  Reference data cannot influence
# interface placement or boundary state construction.
REFERENCE_LOG="$REPORT_DIR/gate1c_reference.log"
printf 'GATE1C_REFERENCE_RUN_ORDER=3\n'
GATE1C_ROLE=reference timeout --signal=TERM 900 \
    "$BUILD_DIR/openfoam/dsmcFoamGate1C" \
    -case "$RUN_DIR/reference" \
    2>&1 | tee "$REFERENCE_LOG"
grep -q 'GATE1C_PASS role=reference' "$REFERENCE_LOG"

SUMMARY="$REPORT_DIR/gate1c_summary.json"
COMPARISON="$REPORT_DIR/gate1c_wall_comparison.csv"
ANALYSIS_LOG="$REPORT_DIR/gate1c_analysis.log"
set +e
python3 "$ROOT/scripts/analyze_gate1c.py" \
    --reference "$REFERENCE_LOG" \
    --hybrid "$HYBRID_LOG" \
    --summary "$SUMMARY" \
    --csv "$COMPARISON" \
    --run-dir "$RUN_DIR" \
    2>&1 | tee "$ANALYSIS_LOG"
analysis_status=${PIPESTATUS[0]}
set -e

printf 'GATE1C_CONTINUUM_LOG=%s\n' "$CONTINUUM_LOG"
printf 'GATE1C_HYBRID_LOG=%s\n' "$HYBRID_LOG"
printf 'GATE1C_REFERENCE_LOG=%s\n' "$REFERENCE_LOG"
printf 'GATE1C_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE1C_COMPARISON=%s\n' "$COMPARISON"
exit "$analysis_status"
