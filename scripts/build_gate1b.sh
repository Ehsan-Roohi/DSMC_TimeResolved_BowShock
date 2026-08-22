#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MUI_PREFIX=${MUI_PREFIX:-"$ROOT/_deps/MUI-install"}
MUI_INCLUDE_DIR_VALUE="$MUI_PREFIX/MUI-2.0.0/include"
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate1b"}

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

if [[ ! -f "$ROOT/reports/gate1a_summary.json" ]] \
    || ! grep -q '"status": "PASS"' "$ROOT/reports/gate1a_summary.json"; then
    printf 'ERROR: Gate 1A PASS artifact is required before Gate 1B.\n' >&2
    exit 2
fi

if [[ ! -r "$MUI_INCLUDE_DIR_VALUE/mui.h" ]]; then
    printf 'ERROR: pinned MUI headers were not found: %s\n' "$MUI_INCLUDE_DIR_VALUE" >&2
    exit 2
fi

if [[ -z "${MPI_ARCH_PATH:-}" ]]; then
    MPI_ARCH_PATH=$(mpic++ --showme:prefix 2>/dev/null || true)
    export MPI_ARCH_PATH
fi
if [[ -z "${MPI_ARCH_PATH:-}" || ! -d "$MPI_ARCH_PATH/include" ]]; then
    printf 'ERROR: MPI_ARCH_PATH could not be resolved from the active MPI.\n' >&2
    exit 2
fi

export MUI_GATE1B_BIN="$BUILD_DIR/openfoam"
export MUI_INCLUDE_DIR="$MUI_INCLUDE_DIR_VALUE"
export MUI_GATE1B_COMMON="$ROOT/openfoam/gate1b/common"
mkdir -p "$MUI_GATE1B_BIN"

for solver in rhoCentralFoamMUI dsmcFoamMUI; do
    source_dir="$ROOT/openfoam/gate1b/$solver"
    wclean "$source_dir" >/dev/null 2>&1 || true
    wmake "$source_dir"
done

for executable in rhoCentralFoamMUI dsmcFoamMUI; do
    if [[ ! -x "$MUI_GATE1B_BIN/$executable" ]]; then
        printf 'ERROR: Gate 1B executable was not built: %s\n' "$executable" >&2
        exit 2
    fi
done

printf 'GATE1B_RHOCENTRAL_EXECUTABLE=%s\n' "$MUI_GATE1B_BIN/rhoCentralFoamMUI"
printf 'GATE1B_DSMC_EXECUTABLE=%s\n' "$MUI_GATE1B_BIN/dsmcFoamMUI"
