#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate1b"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate1b-$RUN_ID"}
mkdir -p "$REPORT_DIR"

# Keep OpenFOAM and MPI in this parent shell for preprocessing and MPMD.
# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate1b.sh"

if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite an existing Gate 1B run: %s\n' "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$RUN_DIR"
cp -a "$ROOT/cases/gate1b/continuum" "$RUN_DIR/continuum"
cp -a "$ROOT/cases/gate1b/dsmc" "$RUN_DIR/dsmc"

blockMesh -case "$RUN_DIR/continuum" \
    > "$REPORT_DIR/gate1b-blockMesh-continuum.log" 2>&1
blockMesh -case "$RUN_DIR/dsmc" \
    > "$REPORT_DIR/gate1b-blockMesh-dsmc.log" 2>&1
dsmcInitialise -case "$RUN_DIR/dsmc" \
    > "$REPORT_DIR/gate1b-dsmcInitialise.log" 2>&1

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 1B runner environment.\n' >&2
    exit 127
fi

LOG="$REPORT_DIR/gate1b_uniform_equilibrium.log"
printf 'GATE1B_MPI_LAUNCHER=%s\n' "$MPI_LAUNCHER"
printf 'GATE1B_RUN_DIR=%s\n' "$RUN_DIR"

timeout --signal=TERM 300 \
    "$MPI_LAUNCHER" \
    -np 1 "$BUILD_DIR/openfoam/rhoCentralFoamMUI" \
        -case "$RUN_DIR/continuum" \
    : \
    -np 1 "$BUILD_DIR/openfoam/dsmcFoamMUI" \
        -case "$RUN_DIR/dsmc" \
    2>&1 | tee "$LOG"

continuum_line=$(grep 'GATE1B_PASS role=continuum' "$LOG" | tail -n 1)
dsmc_line=$(grep 'GATE1B_PASS role=dsmc' "$LOG" | tail -n 1)
handoff_line=$(grep 'GATE1B_DSMC_HANDOFF' "$LOG" | tail -n 1)

continuum_conservation=$(sed -n 's/.*max_conservation_rel=\([^ ]*\).*/\1/p' <<<"$continuum_line")
continuum_cross=$(sed -n 's/.*max_cross_state_rel=\([^ ]*\).*/\1/p' <<<"$continuum_line")
dsmc_conservation=$(sed -n 's/.*max_conservation_rel=\([^ ]*\).*/\1/p' <<<"$dsmc_line")
dsmc_cross=$(sed -n 's/.*max_cross_state_rel=\([^ ]*\).*/\1/p' <<<"$dsmc_line")
parcels=$(sed -n 's/.*parcels=\([^ ]*\).*/\1/p' <<<"$dsmc_line")
handoff_cross=$(sed -n 's/.*initial_cross_rel=\([^ ]*\).*/\1/p' <<<"$handoff_line")

{
    printf '{\n'
    printf '  "gate": "1B",\n'
    printf '  "status": "PASS",\n'
    printf '  "openfoam_version": "%s",\n' "${WM_PROJECT_VERSION:-unknown}"
    printf '  "case": "uniform-periodic-argon",\n'
    printf '  "coupling": "live-two-way-state-audit",\n'
    printf '  "continuum_solver": "rhoCentralFoamMUI",\n'
    printf '  "kinetic_solver": "dsmcFoamMUI",\n'
    printf '  "dsmc_parcels": %s,\n' "${parcels:-null}"
    printf '  "handoff_cross_rel": %s,\n' "${handoff_cross:-null}"
    printf '  "continuum_max_conservation_rel": %s,\n' "${continuum_conservation:-null}"
    printf '  "dsmc_max_conservation_rel": %s,\n' "${dsmc_conservation:-null}"
    printf '  "continuum_max_cross_state_rel": %s,\n' "${continuum_cross:-null}"
    printf '  "dsmc_max_cross_state_rel": %s,\n' "${dsmc_cross:-null}"
    printf '  "run_dir": "%s"\n' "$RUN_DIR"
    printf '}\n'
} > "$REPORT_DIR/gate1b_summary.json"

printf '\nGATE1B_STATUS=PASS\n'
printf 'GATE1B_LOG=%s\n' "$LOG"
printf 'GATE1B_SUMMARY=%s\n' "$REPORT_DIR/gate1b_summary.json"
