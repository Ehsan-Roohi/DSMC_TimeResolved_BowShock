#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3h"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3h-$RUN_ID"}
if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite Gate 3H run directory: %s\n' \
        "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE3H_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f "$REPORT_DIR/gate3h_summary.json" \
    "$REPORT_DIR/gate3h_scaling_1.log" \
    "$REPORT_DIR/gate3h_scaling_2.log" \
    "$REPORT_DIR/gate3h_scaling_4.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
GATE3G_SUMMARY="$REPORT_DIR/gate3g_summary.json"
GATE3C_SUMMARY="$REPORT_DIR/gate3c_physical_summary.json"
GATE3C_COMPARISON="$REPORT_DIR/gate3c_wall_comparison.csv"
STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3g_pass.py" "$GATE3G_SUMMARY"
python3 "$ROOT/scripts/require_gate3c_pass.py" "$GATE3C_SUMMARY"
if [[ ! -s "$GATE3C_COMPARISON" ]]; then
    printf 'ERROR: Gate 3C wall comparison is missing: %s\n' \
        "$GATE3C_COMPARISON" >&2
    exit 2
fi

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate3h
)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3h.sh"

GATE3G_RUN_DIR=$(python3 - "$GATE3G_SUMMARY" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get("run_dir")
if not isinstance(value, str) or not value:
    raise SystemExit("Gate 3G summary has no run_dir")
print(value)
PY
)
case "$GATE3G_RUN_DIR" in
    "$ROOT"/run/gate3g-*) ;;
    *)
        printf 'ERROR: Gate 3G run directory is outside the repository.\n' >&2
        exit 2
        ;;
esac
SOURCE_CASE="$GATE3G_RUN_DIR/continuous"
for case_name in continuum hybrid; do
    if [[ ! -d "$SOURCE_CASE/$case_name" ]]; then
        printf 'ERROR: Gate 3G source case is missing: %s\n' \
            "$SOURCE_CASE/$case_name" >&2
        exit 2
    fi
done

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 3H runner.\n' >&2
    exit 127
fi

prepare_replica() {
    local replicas=$1
    local replica=$2
    local case_root="$RUN_DIR/scaling_${replicas}/replica_${replica}"
    mkdir -p "$case_root"
    cp -a "$SOURCE_CASE/continuum" "$case_root/continuum"
    cp -a "$SOURCE_CASE/hybrid" "$case_root/hybrid"
    local continuum_control="$case_root/continuum/system/controlDict"
    local dsmc_control="$case_root/hybrid/system/controlDict"
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
}

run_scale() {
    local replicas=$1
    local log_file="$REPORT_DIR/gate3h_scaling_${replicas}.log"
    local start_ns end_ns wall_seconds marker replica status
    local -a pids=()
    for ((replica=0; replica<replicas; ++replica)); do
        prepare_replica "$replicas" "$replica"
    done
    start_ns=$(date +%s%N)
    for ((replica=0; replica<replicas; ++replica)); do
        local case_root="$RUN_DIR/scaling_${replicas}/replica_${replica}"
        local session="gate3h_${replicas}_${replica}"
        local segment="scale_${replicas}_${replica}"
        local state_file="$case_root/coupling.state"
        local replica_log="$case_root/replica.log"
        timeout --signal=TERM --kill-after=30 2400 \
            "$MPI_LAUNCHER" \
            -np 1 env \
                GATE3G_COMPARISON="$GATE3C_COMPARISON" \
                GATE3G_CONTINUUM_URI="mpi://continuum/$session" \
                GATE3G_SEGMENT="$segment" \
                GATE3G_START_STEP=0 \
                GATE3G_STOP_STEP=400 \
                "$BUILD_DIR/openfoam/rhoCentralFoamGate3G" \
                -case "$case_root/continuum" \
            : \
            -np 1 env \
                GATE3C_ROLE=live \
                GATE3G_DSMC_URI="mpi://dsmc/$session" \
                GATE3G_SEGMENT="$segment" \
                GATE3G_START_STEP=0 \
                GATE3G_STOP_STEP=400 \
                GATE3G_STATE_FILE="$state_file" \
                "$BUILD_DIR/openfoam/dsmcFoamGate3G" \
                -case "$case_root/hybrid" \
            >"$replica_log" 2>&1 &
        pids+=("$!")
    done
    status=0
    for replica in "${!pids[@]}"; do
        if ! wait "${pids[$replica]}"; then
            status=1
        fi
    done
    end_ns=$(date +%s%N)
    : >"$log_file"
    for ((replica=0; replica<replicas; ++replica)); do
        cat "$RUN_DIR/scaling_${replicas}/replica_${replica}/replica.log" \
            | tee -a "$log_file"
    done
    if (( status != 0 )); then
        return "$status"
    fi
    wall_seconds=$(awk -v start="$start_ns" -v end="$end_ns" \
        'BEGIN {printf "%.9f", (end-start)/1000000000}')
    marker="GATE3H_SCALING replicas=$replicas solver_ranks=$((2*replicas)) steps_per_replica=400 wall_seconds=$wall_seconds"
    printf '%s\n' "$marker" | tee -a "$log_file"
}

for replicas in 1 2 4; do
    STAGE="full_solver_scaling_${replicas}"
    run_scale "$replicas"
done

SUMMARY="$REPORT_DIR/gate3h_summary.json"
STAGE=analysis
python3 "$ROOT/scripts/analyze_gate3h.py" \
    --logs "$REPORT_DIR/gate3h_scaling_1.log" \
           "$REPORT_DIR/gate3h_scaling_2.log" \
           "$REPORT_DIR/gate3h_scaling_4.log" \
    --summary "$SUMMARY" \
    --run-dir "$RUN_DIR"
printf 'GATE3H_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE3H_RUN_DIR=%s\n' "$RUN_DIR"
STAGE=complete
