#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3f"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3f-$RUN_ID"}
if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite Gate 3F run directory: %s\n' \
        "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE3F_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f "$REPORT_DIR/gate3f_summary.json" "$REPORT_DIR/gate3f_live.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
GATE3E_SUMMARY="$REPORT_DIR/gate3e_summary.json"
GATE3C_SUMMARY="$REPORT_DIR/gate3c_physical_summary.json"
GATE3C_COMPARISON="$REPORT_DIR/gate3c_wall_comparison.csv"
STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3e_pass.py" "$GATE3E_SUMMARY"
python3 "$ROOT/scripts/require_gate3c_pass.py" "$GATE3C_SUMMARY"
if [[ ! -s "$GATE3C_COMPARISON" ]]; then
    printf 'ERROR: Gate 3C wall comparison is missing: %s\n' \
        "$GATE3C_COMPARISON" >&2
    exit 2
fi

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate3f
)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3f.sh"

STAGE=case_copy
GATE3E_RUN_DIR=$(python3 - "$GATE3E_SUMMARY" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get("run_dir")
if not isinstance(value, str) or not value:
    raise SystemExit("Gate 3E summary has no run_dir")
print(value)
PY
)
case "$GATE3E_RUN_DIR" in
    "$ROOT"/run/gate3e-*) ;;
    *)
        printf 'ERROR: Gate 3E run directory is outside the repository.\n' >&2
        exit 2
        ;;
esac
for case_name in continuum hybrid; do
    if [[ ! -d "$GATE3E_RUN_DIR/$case_name" ]]; then
        printf 'ERROR: Gate 3E source case is missing: %s\n' \
            "$GATE3E_RUN_DIR/$case_name" >&2
        exit 2
    fi
    cp -a "$GATE3E_RUN_DIR/$case_name" "$RUN_DIR/$case_name"
done

STAGE=case_configuration
CONTINUUM_CONTROL="$RUN_DIR/continuum/system/controlDict"
DSMC_CONTROL="$RUN_DIR/hybrid/system/controlDict"
foamDictionary "$CONTINUUM_CONTROL" -entry application \
    -set rhoCentralFoamGate3F
foamDictionary "$CONTINUUM_CONTROL" -entry startFrom -set latestTime
foamDictionary "$CONTINUUM_CONTROL" -entry endTime -set 1
foamDictionary "$CONTINUUM_CONTROL" -entry deltaT -set 1e-7
foamDictionary "$CONTINUUM_CONTROL" -entry adjustTimeStep -set no
foamDictionary "$CONTINUUM_CONTROL" -entry purgeWrite -set 2
foamDictionary "$DSMC_CONTROL" -entry application -set dsmcFoamGate3F
foamDictionary "$DSMC_CONTROL" -entry startFrom -set latestTime
foamDictionary "$DSMC_CONTROL" -entry endTime -set 1
foamDictionary "$DSMC_CONTROL" -entry deltaT -set 1e-7
foamDictionary "$DSMC_CONTROL" -entry writeInterval -set 200
for control in "$CONTINUUM_CONTROL" "$DSMC_CONTROL"; do
    foamDictionary "$control" -keywords >/dev/null
done

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 3F runner.\n' >&2
    exit 127
fi
LIVE_LOG="$REPORT_DIR/gate3f_live.log"
STAGE=live_dynamic_particle_domain
timeout --signal=TERM --kill-after=30 2400 \
    "$MPI_LAUNCHER" \
    -np 1 env GATE3F_COMPARISON="$GATE3C_COMPARISON" \
        "$BUILD_DIR/openfoam/rhoCentralFoamGate3F" \
        -case "$RUN_DIR/continuum" \
    : \
    -np 1 env GATE3C_ROLE=live \
        "$BUILD_DIR/openfoam/dsmcFoamGate3F" \
        -case "$RUN_DIR/hybrid" \
    2>&1 | tee "$LIVE_LOG"
grep -q 'GATE3F_PASS role=continuum_live' "$LIVE_LOG"
grep -q 'GATE3F_PASS role=dsmc_live' "$LIVE_LOG"

SUMMARY="$REPORT_DIR/gate3f_summary.json"
STAGE=analysis
python3 "$ROOT/scripts/analyze_gate3f.py" \
    --log "$LIVE_LOG" \
    --summary "$SUMMARY" \
    --run-dir "$RUN_DIR"
printf 'GATE3F_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE3F_RUN_DIR=%s\n' "$RUN_DIR"
STAGE=complete
