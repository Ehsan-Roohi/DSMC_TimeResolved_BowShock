#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MUI_PREFIX=${MUI_PREFIX:-"$ROOT/_deps/MUI-install"}
MUI_INCLUDE_DIR_VALUE="$MUI_PREFIX/MUI-2.0.0/include"
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3c"}

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
python3 "$ROOT/scripts/require_gate3b_pilot_pass.py" \
    "$ROOT/reports/gate3b_pilot_summary.json"
if [[ ! -r "$MUI_INCLUDE_DIR_VALUE/mui.h" ]]; then
    printf 'ERROR: pinned MUI headers were not found: %s\n' \
        "$MUI_INCLUDE_DIR_VALUE" >&2
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

export GATE3C_BUILD_DIR="$BUILD_DIR"
export MUI_INCLUDE_DIR="$MUI_INCLUDE_DIR_VALUE"
export MUI_GATE3C_COMMON="$ROOT/openfoam/gate3c/common"
mkdir -p "$GATE3C_BUILD_DIR/openfoam"

for target in muiCylinderContinuumPublisher dsmcFoamGate3C; do
    source_dir="$ROOT/openfoam/gate3c/$target"
    wclean "$source_dir" >/dev/null 2>&1 || true
    wmake "$source_dir"
done

for executable in muiCylinderContinuumPublisher dsmcFoamGate3C; do
    if [[ ! -x "$GATE3C_BUILD_DIR/openfoam/$executable" ]]; then
        printf 'ERROR: Gate 3C executable was not built: %s\n' \
            "$executable" >&2
        exit 2
    fi
done
printf 'GATE3C_PUBLISHER=%s\n' \
    "$GATE3C_BUILD_DIR/openfoam/muiCylinderContinuumPublisher"
printf 'GATE3C_DSMC_EXECUTABLE=%s\n' \
    "$GATE3C_BUILD_DIR/openfoam/dsmcFoamGate3C"
