#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3d"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3d-$RUN_ID"}
if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite Gate 3D run directory: %s\n' \
        "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE3D_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f \
    "$REPORT_DIR/gate3d_summary.json" \
    "$REPORT_DIR/gate3d_continuous.log" \
    "$REPORT_DIR/gate3d_fresh.log" \
    "$REPORT_DIR/gate3d_restart.log" \
    "$REPORT_DIR/gate3d_continuum_feedback.log" \
    "$REPORT_DIR/gate3d_scaling_"*.log

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
GATE3C_SUMMARY="$REPORT_DIR/gate3c_physical_summary.json"
GATE3C_COMPARISON="$REPORT_DIR/gate3c_wall_comparison.csv"
STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3c_pass.py" "$GATE3C_SUMMARY"
if [[ ! -s "$GATE3C_COMPARISON" ]]; then
    printf 'ERROR: Gate 3C physical comparison is missing: %s\n' \
        "$GATE3C_COMPARISON" >&2
    exit 2
fi
if [[ $(wc -l < "$GATE3C_COMPARISON") -ne 65 ]]; then
    printf 'ERROR: Gate 3C comparison must contain one header and 64 faces.\n' >&2
    exit 2
fi

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate3d
)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3d.sh"
MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 3D runner.\n' >&2
    exit 127
fi
MUI_EXE="$BUILD_DIR/mui_physical_feedback"
SCALING_EXE="$BUILD_DIR/physical_feedback_scaling"

run_segment()
{
    local mode=$1
    local input_state=$2
    local output_state=$3
    local output_csv=$4
    local log=$5
    local interface_name="gate3d_${mode}"
    timeout --signal=TERM --kill-after=30 600 \
        "$MPI_LAUNCHER" \
        -np 1 "$MUI_EXE" "mpi://dsmc/$interface_name" \
            dsmc "$mode" "$GATE3C_COMPARISON" - - - \
        : \
        -np 1 "$MUI_EXE" "mpi://continuum/$interface_name" \
            continuum "$mode" "$GATE3C_COMPARISON" \
            "$input_state" "$output_state" "$output_csv" \
        2>&1 | tee "$log"
    grep -q "GATE3D_PASS role=dsmc_replay mode=$mode" "$log"
    grep -q "GATE3D_PASS role=continuum mode=$mode" "$log"
}

CONTINUOUS_STATE="$RUN_DIR/continuous.state"
CONTINUOUS_CSV="$RUN_DIR/continuous_feedback.csv"
CHECKPOINT_STATE="$RUN_DIR/checkpoint.state"
CHECKPOINT_CSV="$RUN_DIR/checkpoint_feedback.csv"
RESUMED_STATE="$RUN_DIR/resumed.state"
RESUMED_CSV="$RUN_DIR/resumed_feedback.csv"
CONTINUOUS_LOG="$REPORT_DIR/gate3d_continuous.log"
FRESH_LOG="$REPORT_DIR/gate3d_fresh.log"
RESTART_LOG="$REPORT_DIR/gate3d_restart.log"
STAGE=continuous_feedback_transport
run_segment continuous - "$CONTINUOUS_STATE" "$CONTINUOUS_CSV" "$CONTINUOUS_LOG"
STAGE=restart_audit
run_segment fresh - "$CHECKPOINT_STATE" "$CHECKPOINT_CSV" "$FRESH_LOG"
run_segment restart "$CHECKPOINT_STATE" "$RESUMED_STATE" "$RESUMED_CSV" "$RESTART_LOG"
cmp -s "$CONTINUOUS_STATE" "$RESUMED_STATE" || {
    printf 'ERROR: Gate 3D continuous and restarted states differ.\n' >&2
    exit 2
}
cmp -s "$CONTINUOUS_CSV" "$RESUMED_CSV" || {
    printf 'ERROR: Gate 3D continuous and restarted feedback CSV files differ.\n' >&2
    exit 2
}

STAGE=continuum_case_copy
GATE3C_RUN_DIR=$(python3 - "$GATE3C_SUMMARY" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get("run_dir")
if not isinstance(value, str) or not value:
    raise SystemExit("Gate 3C summary has no run_dir")
print(value)
PY
)
case "$GATE3C_RUN_DIR" in
    "$ROOT"/run/gate3c-*) ;;
    *)
        printf 'ERROR: Gate 3C run directory is outside the expected repository path.\n' >&2
        exit 2
        ;;
esac
if [[ ! -d "$GATE3C_RUN_DIR/continuum" ]]; then
    printf 'ERROR: Gate 3C continuum case is missing: %s\n' \
        "$GATE3C_RUN_DIR/continuum" >&2
    exit 2
fi
cp -a "$GATE3C_RUN_DIR/continuum" "$RUN_DIR/continuum-feedback"

FEEDBACK_LOG="$REPORT_DIR/gate3d_continuum_feedback.log"
STAGE=openfoam_feedback_application
GATE3D_FEEDBACK_CSV="$CONTINUOUS_CSV" \
    "$BUILD_DIR/openfoam/gate3dContinuumFeedback" \
    -case "$RUN_DIR/continuum-feedback" \
    2>&1 | tee "$FEEDBACK_LOG"
grep -q 'GATE3D_PASS role=continuum_feedback fields_written=true' "$FEEDBACK_LOG"

SCALING_LOGS=()
STAGE=parallel_scaling
for ranks in 1 2 4; do
    log="$REPORT_DIR/gate3d_scaling_${ranks}.log"
    SCALING_LOGS+=("$log")
    timeout --signal=TERM --kill-after=30 300 \
        "$MPI_LAUNCHER" -np "$ranks" \
        "$SCALING_EXE" "$GATE3C_COMPARISON" \
        2>&1 | tee "$log"
    grep -q "GATE3D_SCALING ranks=$ranks " "$log"
done

SUMMARY="$REPORT_DIR/gate3d_summary.json"
STAGE=analysis
analysis_args=(
    --continuous-log "$CONTINUOUS_LOG"
    --fresh-log "$FRESH_LOG"
    --restart-log "$RESTART_LOG"
    --feedback-log "$FEEDBACK_LOG"
    --continuous-state "$CONTINUOUS_STATE"
    --resumed-state "$RESUMED_STATE"
    --continuous-csv "$CONTINUOUS_CSV"
    --resumed-csv "$RESUMED_CSV"
    --summary "$SUMMARY"
    --run-dir "$RUN_DIR"
)
for log in "${SCALING_LOGS[@]}"; do
    analysis_args+=(--scaling-log "$log")
done
python3 "$ROOT/scripts/analyze_gate3d.py" "${analysis_args[@]}"
printf 'GATE3D_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE3D_RUN_DIR=%s\n' "$RUN_DIR"
STAGE=complete
