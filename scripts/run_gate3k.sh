#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3k-$RUN_ID"}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3k-$RUN_ID"}
if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite Gate 3K run directory: %s\n' "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap 'status=$?; if (( status != 0 )); then printf "GATE3K_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2; fi' EXIT
rm -f "$REPORT_DIR/gate3k_summary.json" "$REPORT_DIR/gate3k_continuous.log" \
    "$REPORT_DIR/gate3k_fresh.log" "$REPORT_DIR/gate3k_restart.log" \
    "$REPORT_DIR/gate3k_decomposition.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
GATE3J_RECORD="$ROOT/docs/results/gate3j_unity_63797532.json"
GATE3I_SUMMARY="$REPORT_DIR/gate3i_summary.json"
GATE3C_COMPARISON="$REPORT_DIR/gate3c_wall_comparison.csv"
STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3j_pass.py" "$GATE3J_RECORD"
python3 "$ROOT/scripts/require_gate3i_pass.py" "$GATE3I_SUMMARY"
[[ -s "$GATE3C_COMPARISON" ]] || { echo "ERROR: missing Gate 3C comparison" >&2; exit 2; }

STAGE=static_tests
(cd "$ROOT" && python3 -m unittest -q tests.test_gate3k)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3j.sh"

GATE3I_RUN_DIR=$(python3 - "$GATE3I_SUMMARY" <<'PY'
import json, pathlib, sys
data=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value=data.get("run_dir")
if not isinstance(value,str) or not value:
    raise SystemExit("Gate 3I summary has no run_dir")
print(value)
PY
)
case "$GATE3I_RUN_DIR" in "$ROOT"/run/gate3i-*) ;; *) echo "ERROR: invalid Gate 3I run directory" >&2; exit 2;; esac
SOURCE_ROOT="$GATE3I_RUN_DIR/ranks_1"
for mode in continuous split; do
    mkdir -p "$RUN_DIR/$mode"
    for case_name in continuum hybrid; do
        [[ -d "$SOURCE_ROOT/$case_name" ]] || { echo "ERROR: missing source case $case_name" >&2; exit 2; }
        cp -a "$SOURCE_ROOT/$case_name" "$RUN_DIR/$mode/$case_name"
    done
done

STAGE=case_configuration
for mode in continuous split; do
    cc="$RUN_DIR/$mode/continuum/system/controlDict"
    dc="$RUN_DIR/$mode/hybrid/system/controlDict"
    foamDictionary "$cc" -entry application -set rhoCentralFoamGate3J
    foamDictionary "$cc" -entry startFrom -set latestTime
    foamDictionary "$cc" -entry endTime -set 1
    foamDictionary "$cc" -entry deltaT -set 1e-7
    foamDictionary "$cc" -entry adjustTimeStep -set no
    foamDictionary "$cc" -entry writeControl -set timeStep
    foamDictionary "$cc" -entry writeInterval -set 200
    foamDictionary "$cc" -entry purgeWrite -set 3
    foamDictionary "$dc" -entry application -set dsmcFoamGate3J
    foamDictionary "$dc" -entry startFrom -set latestTime
    foamDictionary "$dc" -entry endTime -set 1
    foamDictionary "$dc" -entry deltaT -set 1e-7
    foamDictionary "$dc" -entry writeControl -set timeStep
    foamDictionary "$dc" -entry writeInterval -set 200
    foamDictionary "$dc" -entry purgeWrite -set 3
done

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
[[ -n "$MPI_LAUNCHER" && -x "$MPI_LAUNCHER" ]] || { echo "ERROR: mpirun unavailable" >&2; exit 127; }

STAGE=field_decomposition
DECOMPOSITION_LOG="$REPORT_DIR/gate3k_decomposition.log"
: >"$DECOMPOSITION_LOG"
for mode in continuous split; do
    for role in continuum dsmc; do
        case_name=continuum; [[ "$role" == dsmc ]] && case_name=hybrid
        case_dir="$RUN_DIR/$mode/$case_name"
        cp "$ROOT/cases/gate3i/decomposeParDict" "$case_dir/system/decomposeParDict"
        foamDictionary "$case_dir/system/decomposeParDict" -entry numberOfSubdomains -set 2
        foamDictionary "$case_dir/system/decomposeParDict" -entry simpleCoeffs/n -set '(2 1 1)'
        decomposePar -case "$case_dir" -force >>"$DECOMPOSITION_LOG" 2>&1
        "$MPI_LAUNCHER" -np 2 checkMesh -parallel -case "$case_dir" -constant >>"$DECOMPOSITION_LOG" 2>&1
        count=$(find "$case_dir" -maxdepth 1 -type d -name 'processor[0-9]*' | wc -l)
        [[ "$count" -eq 2 ]] || { echo "GATE3K_FAIL reason=processor_inventory mode=$mode role=$role"; exit 2; }
        echo "GATE3K_DECOMPOSITION mode=$mode role=$role spatial_ranks=2 fields=true mesh_ok=true" | tee -a "$DECOMPOSITION_LOG"
    done
done

run_pair() {
    local segment=$1 start=$2 stop=$3 case_root=$4 state=$5 log=$6 session=$7
    printf 'GATE3K_LAYOUT segment=%s continuum_ranks=2 dsmc_ranks=2 total_ranks=4 worlds=2\n' "$segment" | tee "$log"
    timeout --signal=TERM --kill-after=30 2400 "$MPI_LAUNCHER" \
      -np 2 env GATE3G_COMPARISON="$GATE3C_COMPARISON" \
        GATE3G_CONTINUUM_URI="mpi://continuum/$session" GATE3G_SEGMENT="$segment" \
        GATE3G_START_STEP="$start" GATE3G_STOP_STEP="$stop" \
        "$BUILD_DIR/openfoam/rhoCentralFoamGate3J" -parallel -world continuum -case "$case_root/continuum" \
      : -np 2 env GATE3C_ROLE=live GATE3G_DSMC_URI="mpi://dsmc/$session" \
        GATE3G_SEGMENT="$segment" GATE3G_START_STEP="$start" GATE3G_STOP_STEP="$stop" \
        GATE3G_STATE_FILE="$state" "$BUILD_DIR/openfoam/dsmcFoamGate3J" \
        -parallel -world dsmc -case "$case_root/hybrid" 2>&1 | tee -a "$log"
    grep -q 'GATE3J_PASS role=continuum_distributed' "$log"
    grep -q 'GATE3J_PASS role=dsmc_distributed' "$log"
}

CONTINUOUS_LOG="$REPORT_DIR/gate3k_continuous.log"
FRESH_LOG="$REPORT_DIR/gate3k_fresh.log"
RESTART_LOG="$REPORT_DIR/gate3k_restart.log"
CONTINUOUS_STATE="$RUN_DIR/continuous.state"
SPLIT_STATE="$RUN_DIR/split.state"
CHECKPOINT_STATE="$RUN_DIR/checkpoint_200.state"

STAGE=continuous
run_pair continuous 0 400 "$RUN_DIR/continuous" "$CONTINUOUS_STATE" "$CONTINUOUS_LOG" gate3k_continuous
STAGE=fresh_segment
run_pair fresh 0 200 "$RUN_DIR/split" "$SPLIT_STATE" "$FRESH_LOG" gate3k_split
cp "$SPLIT_STATE" "$CHECKPOINT_STATE"
STAGE=restart_segment
run_pair restart 200 400 "$RUN_DIR/split" "$SPLIT_STATE" "$RESTART_LOG" gate3k_split
grep -q 'GATE3G_STATE_LOADED step=200 layers=64 accumulators=64' "$RESTART_LOG"

STAGE=analysis
SUMMARY="$REPORT_DIR/gate3k_summary.json"
python3 "$ROOT/scripts/analyze_gate3k.py" --continuous "$CONTINUOUS_LOG" \
    --fresh "$FRESH_LOG" --restart "$RESTART_LOG" --checkpoint "$CHECKPOINT_STATE" \
    --summary "$SUMMARY" --run-dir "$RUN_DIR"
printf 'GATE3K_SUMMARY=%s\nGATE3K_RUN_DIR=%s\n' "$SUMMARY" "$RUN_DIR"
STAGE=complete
