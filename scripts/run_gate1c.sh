#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate1c"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate1c-$RUN_ID"}
mkdir -p "$REPORT_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE1C_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f \
    "$REPORT_DIR/gate1c_summary.json" \
    "$REPORT_DIR/gate1c_wall_comparison.csv" \
    "$REPORT_DIR/gate1c_analysis.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate1c
)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate1c.sh"
STAGE=case_generation
python3 "$ROOT/scripts/generate_gate1c_cases.py" "$RUN_DIR"

STAGE=dictionary_validation
dictionary_count=0
while IFS= read -r dictionary_file; do
    if ! foamDictionary "$dictionary_file" -keywords >/dev/null; then
        printf 'ERROR: generated OpenFOAM dictionary is invalid: %s\n' \
            "$dictionary_file" >&2
        exit 2
    fi
    dictionary_count=$((dictionary_count + 1))
done < <(find "$RUN_DIR" -type f -print | sort)
printf 'GATE1C_DICTIONARIES_VALIDATED=%d\n' "$dictionary_count"
if (( dictionary_count != 44 )); then
    printf 'ERROR: generated Gate 1C file inventory is incomplete: expected 44, got %d.\n' \
        "$dictionary_count" >&2
    exit 2
fi

if ! grep -Fq 'div(tauMC) Gauss linear;' \
    "$RUN_DIR/continuum/system/fvSchemes"; then
    printf 'ERROR: required rhoCentralFoam div(tauMC) scheme is missing.\n' >&2
    exit 2
fi

STAGE=block_mesh
for case_name in continuum hybrid reference; do
    setup_log="$REPORT_DIR/gate1c-blockMesh-$case_name.log"
    if ! blockMesh -case "$RUN_DIR/$case_name" > "$setup_log" 2>&1; then
        cat "$setup_log" >&2
        exit 2
    fi
done
STAGE=dsmc_initialise
for case_name in hybrid reference; do
    setup_log="$REPORT_DIR/gate1c-dsmcInitialise-$case_name.log"
    if ! dsmcInitialise -case "$RUN_DIR/$case_name" > "$setup_log" 2>&1; then
        cat "$setup_log" >&2
        exit 2
    fi
done

CONTINUUM_LOG="$REPORT_DIR/gate1c_continuum.log"
printf 'GATE1C_CONTINUUM_RUN_ORDER=1\n'
STAGE=continuum
timeout --signal=TERM --kill-after=30 900 \
    rhoCentralFoam -case "$RUN_DIR/continuum" \
    2>&1 | tee "$CONTINUUM_LOG"

# The publisher must read the converged snapshot, not the initial fields.
STAGE=publisher_setup
CONTINUUM_CONTROL="$RUN_DIR/continuum/system/controlDict"
foamDictionary "$CONTINUUM_CONTROL" -entry startFrom -set latestTime
START_FROM=$(
    foamDictionary "$CONTINUUM_CONTROL" -entry startFrom -value \
    | tr -d '[:space:]'
)
if [[ "$START_FROM" != "latestTime" ]]; then
    printf 'ERROR: failed to set continuum publisher startFrom=latestTime.\n' >&2
    exit 2
fi
printf 'GATE1C_PUBLISHER_START_FROM=%s\n' "$START_FROM"

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 1C runner.\n' >&2
    exit 127
fi

HYBRID_LOG="$REPORT_DIR/gate1c_hybrid.log"
printf 'GATE1C_HYBRID_RUN_ORDER=2\n'
STAGE=hybrid
timeout --signal=TERM --kill-after=30 900 \
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
STAGE=reference
GATE1C_ROLE=reference timeout --signal=TERM --kill-after=30 900 \
    "$BUILD_DIR/openfoam/dsmcFoamGate1C" \
    -case "$RUN_DIR/reference" \
    2>&1 | tee "$REFERENCE_LOG"
grep -q 'GATE1C_PASS role=reference' "$REFERENCE_LOG"

SUMMARY="$REPORT_DIR/gate1c_summary.json"
COMPARISON="$REPORT_DIR/gate1c_wall_comparison.csv"
ANALYSIS_LOG="$REPORT_DIR/gate1c_analysis.log"
STAGE=analysis
set +e
python3 "$ROOT/scripts/analyze_gate1c.py" \
    --reference "$REFERENCE_LOG" \
    --hybrid "$HYBRID_LOG" \
    --summary "$SUMMARY" \
    --csv "$COMPARISON" \
    --run-dir "$RUN_DIR" \
    2>&1 | tee "$ANALYSIS_LOG"
analysis_pipeline_status=("${PIPESTATUS[@]}")
analysis_status=${analysis_pipeline_status[0]}
if (( analysis_status == 0 && analysis_pipeline_status[1] != 0 )); then
    analysis_status=${analysis_pipeline_status[1]}
fi
set -e

printf 'GATE1C_CONTINUUM_LOG=%s\n' "$CONTINUUM_LOG"
printf 'GATE1C_HYBRID_LOG=%s\n' "$HYBRID_LOG"
printf 'GATE1C_REFERENCE_LOG=%s\n' "$REFERENCE_LOG"
printf 'GATE1C_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE1C_COMPARISON=%s\n' "$COMPARISON"
if (( analysis_status == 0 )); then
    STAGE=complete
fi
exit "$analysis_status"
