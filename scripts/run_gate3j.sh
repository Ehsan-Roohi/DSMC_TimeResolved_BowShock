#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3j-$RUN_ID"}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3j-$RUN_ID"}
if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite Gate 3J run directory: %s\n' \
        "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE3J_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f "$REPORT_DIR/gate3j_summary.json" \
    "$REPORT_DIR/gate3j_live.log" \
    "$REPORT_DIR/gate3j_decomposition.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
GATE3I_SUMMARY="$REPORT_DIR/gate3i_summary.json"
GATE3C_COMPARISON="$REPORT_DIR/gate3c_wall_comparison.csv"
STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3i_pass.py" "$GATE3I_SUMMARY"
if [[ ! -s "$GATE3C_COMPARISON" ]]; then
    printf 'ERROR: Gate 3C wall comparison is missing: %s\n' \
        "$GATE3C_COMPARISON" >&2
    exit 2
fi

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate3j
)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3j.sh"

GATE3I_RUN_DIR=$(python3 - "$GATE3I_SUMMARY" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get("run_dir")
if not isinstance(value, str) or not value:
    raise SystemExit("Gate 3I summary has no run_dir")
print(value)
PY
)
case "$GATE3I_RUN_DIR" in
    "$ROOT"/run/gate3i-*) ;;
    *)
        printf 'ERROR: Gate 3I run directory is outside the repository.\n' >&2
        exit 2
        ;;
esac
SOURCE_ROOT="$GATE3I_RUN_DIR/ranks_1"
for case_name in continuum hybrid; do
    if [[ ! -d "$SOURCE_ROOT/$case_name" ]]; then
        printf 'ERROR: Gate 3I source case is missing: %s\n' \
            "$SOURCE_ROOT/$case_name" >&2
        exit 2
    fi
    cp -a "$SOURCE_ROOT/$case_name" "$RUN_DIR/$case_name"
done

STAGE=case_configuration
continuum_control="$RUN_DIR/continuum/system/controlDict"
dsmc_control="$RUN_DIR/hybrid/system/controlDict"
foamDictionary "$continuum_control" -entry application \
    -set rhoCentralFoamGate3J
foamDictionary "$continuum_control" -entry startFrom -set latestTime
foamDictionary "$continuum_control" -entry endTime -set 1
foamDictionary "$continuum_control" -entry deltaT -set 1e-7
foamDictionary "$continuum_control" -entry adjustTimeStep -set no
foamDictionary "$continuum_control" -entry writeControl -set timeStep
foamDictionary "$continuum_control" -entry writeInterval -set 200
foamDictionary "$continuum_control" -entry purgeWrite -set 2
foamDictionary "$dsmc_control" -entry application -set dsmcFoamGate3J
foamDictionary "$dsmc_control" -entry startFrom -set latestTime
foamDictionary "$dsmc_control" -entry endTime -set 1
foamDictionary "$dsmc_control" -entry deltaT -set 1e-7
foamDictionary "$dsmc_control" -entry writeControl -set timeStep
foamDictionary "$dsmc_control" -entry writeInterval -set 200
foamDictionary "$dsmc_control" -entry purgeWrite -set 2

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 3J runner.\n' >&2
    exit 127
fi

STAGE=field_decomposition
DECOMPOSITION_LOG="$REPORT_DIR/gate3j_decomposition.log"
: >"$DECOMPOSITION_LOG"
for role in continuum dsmc; do
    case_name=continuum
    [[ "$role" == dsmc ]] && case_name=hybrid
    case_dir="$RUN_DIR/$case_name"
    cp "$ROOT/cases/gate3i/decomposeParDict" \
        "$case_dir/system/decomposeParDict"
    foamDictionary "$case_dir/system/decomposeParDict" \
        -entry numberOfSubdomains -set 2
    foamDictionary "$case_dir/system/decomposeParDict" \
        -entry simpleCoeffs/n -set '(2 1 1)'
    decomposePar -case "$case_dir" -force \
        >>"$DECOMPOSITION_LOG" 2>&1
    "$MPI_LAUNCHER" -np 2 checkMesh -parallel -case "$case_dir" -constant \
        >>"$DECOMPOSITION_LOG" 2>&1
    processor_dirs=$(find "$case_dir" -maxdepth 1 -type d \
        -name 'processor[0-9]*' | wc -l)
    if [[ "$processor_dirs" -ne 2 ]]; then
        printf 'GATE3J_FAIL reason=processor_inventory role=%s actual=%s\n' \
            "$role" "$processor_dirs" | tee -a "$DECOMPOSITION_LOG"
        exit 2
    fi
    printf 'GATE3J_DECOMPOSITION role=%s spatial_ranks=2 fields=true mesh_ok=true\n' \
        "$role" | tee -a "$DECOMPOSITION_LOG"
done

STAGE=live_distributed_solvers
LIVE_LOG="$REPORT_DIR/gate3j_live.log"
STATE_FILE="$RUN_DIR/gate3j.state"
printf 'GATE3J_LAYOUT continuum_ranks=2 dsmc_ranks=2 total_ranks=4 worlds=2\n' \
    | tee "$LIVE_LOG"
timeout --signal=TERM --kill-after=30 2400 \
    "$MPI_LAUNCHER" \
    -np 2 env \
        GATE3G_COMPARISON="$GATE3C_COMPARISON" \
        GATE3G_CONTINUUM_URI=mpi://continuum/gate3j \
        GATE3G_SEGMENT=gate3j \
        GATE3G_START_STEP=0 \
        GATE3G_STOP_STEP=200 \
        "$BUILD_DIR/openfoam/rhoCentralFoamGate3J" \
        -parallel -world continuum -case "$RUN_DIR/continuum" \
    : \
    -np 2 env \
        GATE3C_ROLE=live \
        GATE3G_DSMC_URI=mpi://dsmc/gate3j \
        GATE3G_SEGMENT=gate3j \
        GATE3G_START_STEP=0 \
        GATE3G_STOP_STEP=200 \
        GATE3G_STATE_FILE="$STATE_FILE" \
        "$BUILD_DIR/openfoam/dsmcFoamGate3J" \
        -parallel -world dsmc -case "$RUN_DIR/hybrid" \
    2>&1 | tee -a "$LIVE_LOG"
grep -q 'GATE3J_PASS role=continuum_distributed' "$LIVE_LOG"
grep -q 'GATE3J_PASS role=dsmc_distributed' "$LIVE_LOG"

SUMMARY="$REPORT_DIR/gate3j_summary.json"
STAGE=analysis
python3 "$ROOT/scripts/analyze_gate3j.py" \
    --live "$LIVE_LOG" \
    --decomposition "$DECOMPOSITION_LOG" \
    --summary "$SUMMARY" \
    --run-dir "$RUN_DIR"
printf 'GATE3J_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE3J_RUN_DIR=%s\n' "$RUN_DIR"
STAGE=complete
