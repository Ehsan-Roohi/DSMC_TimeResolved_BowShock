#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate2"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate2-$RUN_ID"}
mkdir -p "$REPORT_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE2_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f \
    "$REPORT_DIR/gate2_summary.json" \
    "$REPORT_DIR/gate2_indicator.csv" \
    "$REPORT_DIR/gate2_analysis.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q \
        tests.test_gate2 tests.test_gate2_time_precision
)

STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate2.sh"
STAGE=case_generation
python3 "$ROOT/scripts/generate_gate2_cases.py" "$RUN_DIR"

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
printf 'GATE2_DICTIONARIES_VALIDATED=%d\n' "$dictionary_count"
if (( dictionary_count != 28 )); then
    printf 'ERROR: generated Gate 2 inventory is incomplete: expected 28, got %d.\n' \
        "$dictionary_count" >&2
    exit 2
fi

PROPERTIES="$RUN_DIR/adaptive/system/gate2Properties"
ACTIVATION=$(foamDictionary "$PROPERTIES" -entry activationThreshold -value)
DEACTIVATION=$(foamDictionary "$PROPERTIES" -entry deactivationThreshold -value)
python3 - "$ACTIVATION" "$DEACTIVATION" <<'PY'
import sys
activate, deactivate = map(float, sys.argv[1:])
if not activate > deactivate >= 0.0:
    raise SystemExit("invalid Gate 2 hysteresis thresholds")
PY
printf 'GATE2_HYSTERESIS activation=%s deactivation=%s\n' \
    "$ACTIVATION" "$DEACTIVATION"

STAGE=block_mesh
for case_name in continuum adaptive; do
    setup_log="$REPORT_DIR/gate2-blockMesh-$case_name.log"
    if ! blockMesh -case "$RUN_DIR/$case_name" >"$setup_log" 2>&1; then
        cat "$setup_log" >&2
        exit 2
    fi
done
STAGE=dsmc_initialise
INITIALISE_LOG="$REPORT_DIR/gate2-dsmcInitialise.log"
if ! dsmcInitialise -case "$RUN_DIR/adaptive" >"$INITIALISE_LOG" 2>&1; then
    cat "$INITIALISE_LOG" >&2
    exit 2
fi

CONTINUUM_LOG="$REPORT_DIR/gate2_continuum.log"
STAGE=continuum
timeout --signal=TERM --kill-after=30 900 \
    rhoCentralFoam -case "$RUN_DIR/continuum" \
    2>&1 | tee "$CONTINUUM_LOG"

STAGE=snapshot_inventory
mapfile -t SNAPSHOTS < <(
    foamListTimes -case "$RUN_DIR/continuum" -withZero \
        | sed '/^[[:space:]]*$/d' | sort -g
)
printf 'GATE2_SNAPSHOTS=%s\n' "${SNAPSHOTS[*]}"
if (( ${#SNAPSHOTS[@]} != 5 )); then
    printf 'ERROR: expected five continuum snapshots, got %d.\n' \
        "${#SNAPSHOTS[@]}" >&2
    exit 2
fi
for snapshot in "${SNAPSHOTS[@]}"; do
    for field in p T U; do
        if [[ ! -r "$RUN_DIR/continuum/$snapshot/$field" ]]; then
            printf 'ERROR: exact snapshot field is missing: %s/%s\n' \
                "$snapshot" "$field" >&2
            exit 2
        fi
    done
done

REPLAY=("${SNAPSHOTS[@]}")
for ((index=${#SNAPSHOTS[@]}-2; index>=0; --index)); do
    REPLAY+=("${SNAPSHOTS[index]}")
done
if (( ${#REPLAY[@]} != 9 )); then
    printf 'ERROR: Gate 2 replay must contain nine frames.\n' >&2
    exit 2
fi

CONTROL="$RUN_DIR/continuum/system/controlDict"
TIME_SETTER="$ROOT/scripts/set_openfoam_start_time.py"
foamDictionary "$CONTROL" -entry startFrom -set startTime
INDICATOR_CSV="$REPORT_DIR/gate2_indicator.csv"
INDICATOR_LOG="$REPORT_DIR/gate2_indicator.log"
: >"$INDICATOR_LOG"
STAGE=indicator
for frame in "${!REPLAY[@]}"; do
    snapshot=${REPLAY[frame]}
    python3 "$TIME_SETTER" "$CONTROL" "$snapshot"
    GATE2_FRAME="$frame" GATE2_INDICATOR_OUTPUT="$INDICATOR_CSV" \
        "$BUILD_DIR/openfoam/gate2ContinuumIndicator" \
        -case "$RUN_DIR/continuum" \
        2>&1 | tee -a "$INDICATOR_LOG"
    grep -q "GATE2_PASS role=indicator frame=$frame" "$INDICATOR_LOG"
done
if [[ $(wc -l <"$INDICATOR_CSV") -ne 7201 ]]; then
    printf 'ERROR: Gate 2 indicator CSV must contain 7201 lines.\n' >&2
    exit 2
fi

MANAGER_LOG="$REPORT_DIR/gate2_particle_manager.log"
STAGE=particle_manager
GATE2_INDICATOR_CSV="$INDICATOR_CSV" \
    timeout --signal=TERM --kill-after=30 300 \
    "$BUILD_DIR/openfoam/gate2ParticleManager" \
    -case "$RUN_DIR/adaptive" \
    2>&1 | tee "$MANAGER_LOG"
grep -q 'GATE2_PASS role=particle_manager' "$MANAGER_LOG"

SUMMARY="$REPORT_DIR/gate2_summary.json"
ANALYSIS_LOG="$REPORT_DIR/gate2_analysis.log"
STAGE=analysis
python3 "$ROOT/scripts/analyze_gate2.py" \
    --log "$MANAGER_LOG" \
    --indicator "$INDICATOR_CSV" \
    --summary "$SUMMARY" \
    --run-dir "$RUN_DIR" \
    2>&1 | tee "$ANALYSIS_LOG"

printf 'GATE2_CONTINUUM_LOG=%s\n' "$CONTINUUM_LOG"
printf 'GATE2_INDICATOR_LOG=%s\n' "$INDICATOR_LOG"
printf 'GATE2_PARTICLE_LOG=%s\n' "$MANAGER_LOG"
printf 'GATE2_SUMMARY=%s\n' "$SUMMARY"
STAGE=complete
