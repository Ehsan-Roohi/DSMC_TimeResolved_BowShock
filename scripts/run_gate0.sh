#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate0"}
mkdir -p "$REPORT_DIR"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

bash "$ROOT/scripts/unity_probe.sh"

missing_commands=()
for command_name in wmake rhoCentralFoam dsmcFoam mpic++ mpirun; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        missing_commands+=("$command_name")
    fi
done

if (( ${#missing_commands[@]} > 0 )); then
    printf 'ERROR: Gate 0 environment is missing required commands:' >&2
    printf ' %s' "${missing_commands[@]}" >&2
    printf '\n' >&2
    exit 2
fi

if [[ -z "${WM_PROJECT_DIR:-}" || ! -d "$WM_PROJECT_DIR/applications" ]]; then
    printf 'ERROR: WM_PROJECT_DIR/applications is unavailable after loading OpenFOAM.\n' >&2
    exit 2
fi

rho_source=$(find "$WM_PROJECT_DIR/applications" -type f -path '*rhoCentralFoam*' -print -quit 2>/dev/null || true)
dsmc_source=$(find "$WM_PROJECT_DIR/applications" -type f -path '*dsmcFoam*' -print -quit 2>/dev/null || true)
if [[ -z "$rho_source" || -z "$dsmc_source" ]]; then
    printf 'ERROR: Gate 0 requires installed rhoCentralFoam and dsmcFoam source trees.\n' >&2
    printf 'rhoCentralFoam_source=%s\n' "${rho_source:-NOT_FOUND}" >&2
    printf 'dsmcFoam_source=%s\n' "${dsmc_source:-NOT_FOUND}" >&2
    exit 2
fi

printf 'GATE0_ENVIRONMENT=PASS\n'
printf 'RHO_CENTRAL_SOURCE=%s\n' "$rho_source"
printf 'DSMC_SOURCE=%s\n' "$dsmc_source"

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
    printf '  "openfoam_project": "%s",\n' "${WM_PROJECT:-unknown}"
    printf '  "openfoam_version": "%s",\n' "${WM_PROJECT_VERSION:-unknown}"
    printf '  "state_fields": ["rho", "Ux", "Uy", "Uz", "T"]\n'
    printf '}\n'
} > "$REPORT_DIR/gate0_summary.json"

printf '\nGATE0_STATUS=PASS\n'
printf 'GATE0_LOG=%s\n' "$LOG"
printf 'GATE0_SUMMARY=%s\n' "$REPORT_DIR/gate0_summary.json"
printf 'PREFLIGHT_REPORT=%s\n' "$REPORT_DIR/unity_preflight.txt"
