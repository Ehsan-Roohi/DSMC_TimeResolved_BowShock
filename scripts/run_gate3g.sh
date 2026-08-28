#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3g"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3g-$RUN_ID"}
if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite Gate 3G run directory: %s\n' \
        "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE3G_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f "$REPORT_DIR/gate3g_summary.json" \
    "$REPORT_DIR/gate3g_continuous.log" \
    "$REPORT_DIR/gate3g_fresh.log" \
    "$REPORT_DIR/gate3g_restart.log" \
    "$REPORT_DIR/gate3g_scaling_1.log" \
    "$REPORT_DIR/gate3g_scaling_2.log" \
    "$REPORT_DIR/gate3g_scaling_4.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
GATE3F_SUMMARY="$REPORT_DIR/gate3f_summary.json"
GATE3C_SUMMARY="$REPORT_DIR/gate3c_physical_summary.json"
GATE3C_COMPARISON="$REPORT_DIR/gate3c_wall_comparison.csv"
STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3f_pass.py" "$GATE3F_SUMMARY"
python3 "$ROOT/scripts/require_gate3c_pass.py" "$GATE3C_SUMMARY"
if [[ ! -s "$GATE3C_COMPARISON" ]]; then
    printf 'ERROR: Gate 3C wall comparison is missing: %s\n' \
        "$GATE3C_COMPARISON" >&2
    exit 2
fi

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate3g
)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3g.sh"

STAGE=case_copy
GATE3F_RUN_DIR=$(python3 - "$GATE3F_SUMMARY" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get("run_dir")
if not isinstance(value, str) or not value:
    raise SystemExit("Gate 3F summary has no run_dir")
print(value)
PY
)
case "$GATE3F_RUN_DIR" in
    "$ROOT"/run/gate3f-*) ;;
    *)
        printf 'ERROR: Gate 3F run directory is outside the repository.\n' >&2
        exit 2
        ;;
esac
for mode in continuous split; do
    mkdir -p "$RUN_DIR/$mode"
    for case_name in continuum hybrid; do
        if [[ ! -d "$GATE3F_RUN_DIR/$case_name" ]]; then
            printf 'ERROR: Gate 3F source case is missing: %s\n' \
                "$GATE3F_RUN_DIR/$case_name" >&2
            exit 2
        fi
        cp -a "$GATE3F_RUN_DIR/$case_name" "$RUN_DIR/$mode/$case_name"
    done
done

STAGE=case_configuration
for mode in continuous split; do
    continuum_control="$RUN_DIR/$mode/continuum/system/controlDict"
    dsmc_control="$RUN_DIR/$mode/hybrid/system/controlDict"
    foamDictionary "$continuum_control" -entry application \
        -set rhoCentralFoamGate3G
    foamDictionary "$continuum_control" -entry startFrom -set latestTime
    foamDictionary "$continuum_control" -entry endTime -set 1
    foamDictionary "$continuum_control" -entry deltaT -set 1e-7
    foamDictionary "$continuum_control" -entry adjustTimeStep -set no
    foamDictionary "$continuum_control" -entry writeControl -set timeStep
    foamDictionary "$continuum_control" -entry writeInterval -set 200
    foamDictionary "$continuum_control" -entry purgeWrite -set 2
    foamDictionary "$dsmc_control" -entry application -set dsmcFoamGate3G
    foamDictionary "$dsmc_control" -entry startFrom -set latestTime
    foamDictionary "$dsmc_control" -entry endTime -set 1
    foamDictionary "$dsmc_control" -entry deltaT -set 1e-7
    foamDictionary "$dsmc_control" -entry writeControl -set timeStep
    foamDictionary "$dsmc_control" -entry writeInterval -set 200
    foamDictionary "$dsmc_control" -entry purgeWrite -set 2
    foamDictionary "$continuum_control" -keywords >/dev/null
    foamDictionary "$dsmc_control" -keywords >/dev/null
done

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 3G runner.\n' >&2
    exit 127
fi

run_pair() {
    local segment=$1
    local start_step=$2
    local stop_step=$3
    local case_root=$4
    local state_file=$5
    local log_file=$6
    local session=$7
    timeout --signal=TERM --kill-after=30 2400 \
        "$MPI_LAUNCHER" \
        -np 1 env \
            GATE3G_COMPARISON="$GATE3C_COMPARISON" \
            GATE3G_CONTINUUM_URI="mpi://continuum/$session" \
            GATE3G_SEGMENT="$segment" \
            GATE3G_START_STEP="$start_step" \
            GATE3G_STOP_STEP="$stop_step" \
            "$BUILD_DIR/openfoam/rhoCentralFoamGate3G" \
            -case "$case_root/continuum" \
        : \
        -np 1 env \
            GATE3C_ROLE=live \
            GATE3G_DSMC_URI="mpi://dsmc/$session" \
            GATE3G_SEGMENT="$segment" \
            GATE3G_START_STEP="$start_step" \
            GATE3G_STOP_STEP="$stop_step" \
            GATE3G_STATE_FILE="$state_file" \
            "$BUILD_DIR/openfoam/dsmcFoamGate3G" \
            -case "$case_root/hybrid" \
        2>&1 | tee "$log_file"
}

CONTINUOUS_LOG="$REPORT_DIR/gate3g_continuous.log"
FRESH_LOG="$REPORT_DIR/gate3g_fresh.log"
RESTART_LOG="$REPORT_DIR/gate3g_restart.log"
CONTINUOUS_STATE="$RUN_DIR/continuous.state"
SPLIT_STATE="$RUN_DIR/split.state"
CHECKPOINT_STATE="$RUN_DIR/checkpoint_600.state"

STAGE=continuous
run_pair continuous 0 1000 "$RUN_DIR/continuous" \
    "$CONTINUOUS_STATE" "$CONTINUOUS_LOG" gate3g_continuous
grep -q 'GATE3G_PASS role=continuum_live segment=continuous' "$CONTINUOUS_LOG"
grep -q 'GATE3G_PASS role=dsmc_live segment=continuous' "$CONTINUOUS_LOG"

STAGE=fresh_segment
run_pair fresh 0 600 "$RUN_DIR/split" \
    "$SPLIT_STATE" "$FRESH_LOG" gate3g_split
grep -q 'GATE3G_PASS role=continuum_live segment=fresh' "$FRESH_LOG"
grep -q 'GATE3G_PASS role=dsmc_live segment=fresh' "$FRESH_LOG"
cp "$SPLIT_STATE" "$CHECKPOINT_STATE"

STAGE=restart_segment
run_pair restart 600 1000 "$RUN_DIR/split" \
    "$SPLIT_STATE" "$RESTART_LOG" gate3g_split
grep -q 'GATE3G_STATE_LOADED step=600' "$RESTART_LOG"
grep -q 'GATE3G_PASS role=continuum_live segment=restart' "$RESTART_LOG"
grep -q 'GATE3G_PASS role=dsmc_live segment=restart' "$RESTART_LOG"

STAGE=scaling
SCALING_EXECUTABLE="$BUILD_DIR/core/dynamic_restart_scaling"
for ranks in 1 2 4; do
    scaling_log="$REPORT_DIR/gate3g_scaling_${ranks}.log"
    "$MPI_LAUNCHER" -np "$ranks" "$SCALING_EXECUTABLE" \
        2>&1 | tee "$scaling_log"
    grep -q "GATE3G_SCALING ranks=$ranks " "$scaling_log"
done

SUMMARY="$REPORT_DIR/gate3g_summary.json"
STAGE=analysis
python3 "$ROOT/scripts/analyze_gate3g.py" \
    --continuous "$CONTINUOUS_LOG" \
    --fresh "$FRESH_LOG" \
    --restart "$RESTART_LOG" \
    --checkpoint "$CHECKPOINT_STATE" \
    --scaling "$REPORT_DIR/gate3g_scaling_1.log" \
              "$REPORT_DIR/gate3g_scaling_2.log" \
              "$REPORT_DIR/gate3g_scaling_4.log" \
    --summary "$SUMMARY" \
    --run-dir "$RUN_DIR"
printf 'GATE3G_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE3G_RUN_DIR=%s\n' "$RUN_DIR"
STAGE=complete
