#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate1a"}
mkdir -p "$REPORT_DIR"

# The build is deliberately isolated in a child shell. Load OpenFOAM/MPI in
# this runner as well so that the MPMD launcher remains on PATH afterwards.
# shellcheck source=scripts/load_openfoam_if_needed.sh
source "$ROOT/scripts/load_openfoam_if_needed.sh"

BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate1a.sh"

EXE="$BUILD_DIR/mui_fixed_interface"
LOG="$REPORT_DIR/gate1a_fixed_interface.log"
MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}

if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 1A runner environment.\n' >&2
    exit 127
fi

printf 'GATE1A_MPI_LAUNCHER=%s\n' "$MPI_LAUNCHER"
"$MPI_LAUNCHER" \
    -np 1 "$EXE" mpi://continuum/fixedInterface continuum \
    : \
    -np 1 "$EXE" mpi://dsmc/fixedInterface dsmc \
    2>&1 | tee "$LOG"

grep -q 'GATE1A_OPENFOAM_API_PASS' "$REPORT_DIR/gate1a-openfoam-probe.capture" 2>/dev/null \
    || "$BUILD_DIR/openfoam/muiOpenFoamApiProbe" \
        | tee "$REPORT_DIR/gate1a-openfoam-probe.capture"
grep -q 'GATE1A_PASS role=continuum' "$LOG"
grep -q 'GATE1A_PASS role=dsmc' "$LOG"
grep -q 'GATE1A_TRANSFER_PASS' "$LOG"
grep -q 'GATE1A_MAXWELLIAN_PASS' "$LOG"

max_moment_rel=$(sed -n 's/.*max_moment_rel=\([^ ]*\).*/\1/p' "$LOG" | tail -n 1)
max_state_abs=$(sed -n 's/.*max_state_abs=\([^ ]*\).*/\1/p' "$LOG" | tail -n 1)

{
    printf '{\n'
    printf '  "gate": "1A",\n'
    printf '  "status": "PASS",\n'
    printf '  "openfoam_version": "%s",\n' "${WM_PROJECT_VERSION:-unknown}"
    printf '  "interface": "fixed",\n'
    printf '  "direction": "rhoCentralFoam-to-dsmcFoam",\n'
    printf '  "max_state_abs": %s,\n' "${max_state_abs:-null}"
    printf '  "max_moment_rel": %s,\n' "${max_moment_rel:-null}"
    printf '  "particles_per_face": 6,\n'
    printf '  "production_case_submitted": false\n'
    printf '}\n'
} > "$REPORT_DIR/gate1a_summary.json"

printf '\nGATE1A_STATUS=PASS\n'
printf 'GATE1A_LOG=%s\n' "$LOG"
printf 'GATE1A_SUMMARY=%s\n' "$REPORT_DIR/gate1a_summary.json"
