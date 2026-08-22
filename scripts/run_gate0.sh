#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate0"}
mkdir -p "$REPORT_DIR"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

bash "$ROOT/scripts/unity_probe.sh"
bash "$ROOT/scripts/build_gate0.sh"

if command -v mpirun >/dev/null 2>&1; then
    MPI_LAUNCHER=mpirun
elif command -v mpiexec >/dev/null 2>&1; then
    MPI_LAUNCHER=mpiexec
else
    printf 'ERROR: neither mpirun nor mpiexec is available\n' >&2
    exit 2
fi

EXE="$BUILD_DIR/mui_state_exchange"
LOG="$REPORT_DIR/gate0_mui_exchange.log"

"$MPI_LAUNCHER" \
    -np 1 "$EXE" mpi://continuum/dsmcNS continuum \
    : \
    -np 1 "$EXE" mpi://dsmc/dsmcNS dsmc \
    2>&1 | tee "$LOG"

grep -q 'GATE0_PASS role=continuum' "$LOG"
grep -q 'GATE0_PASS role=dsmc' "$LOG"

{
    printf '{\n'
    printf '  "gate": 0,\n'
    printf '  "status": "PASS",\n'
    printf '  "mui_commit": "b130c7a12aa8e7ac8d54e9188c4836342daed263",\n'
    printf '  "state_fields": ["rho", "Ux", "Uy", "Uz", "T"]\n'
    printf '}\n'
} > "$REPORT_DIR/gate0_summary.json"

printf '\nGATE0_STATUS=PASS\n'
printf 'GATE0_LOG=%s\n' "$LOG"
printf 'GATE0_SUMMARY=%s\n' "$REPORT_DIR/gate0_summary.json"
printf 'PREFLIGHT_REPORT=%s\n' "$REPORT_DIR/unity_preflight.txt"
