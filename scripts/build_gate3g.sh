#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MUI_PREFIX=${MUI_PREFIX:-"$ROOT/_deps/MUI-install"}
MUI_INCLUDE_DIR_VALUE="$MUI_PREFIX/MUI-2.0.0/include"
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3g"}

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
python3 "$ROOT/scripts/require_gate3f_pass.py" \
    "$ROOT/reports/gate3f_summary.json"
for command_name in cmake mpic++ wmake; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'ERROR: required Gate 3G build command not found: %s\n' \
            "$command_name" >&2
        exit 2
    fi
done
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

CORE_BUILD="$BUILD_DIR/core"
cmake -S "$ROOT" -B "$CORE_BUILD" \
    -DBUILD_MUI_GATE0=OFF \
    -DBUILD_GATE3G_SCALING=ON \
    -DBUILD_CORE_TESTS=ON
cmake --build "$CORE_BUILD" --parallel 2
ctest --test-dir "$CORE_BUILD" --output-on-failure

export GATE3G_BUILD_DIR="$BUILD_DIR"
export MUI_INCLUDE_DIR="$MUI_INCLUDE_DIR_VALUE"
export MUI_GATE1B_COMMON="$ROOT/openfoam/gate1b/common"
export MUI_GATE3C_COMMON="$ROOT/openfoam/gate3c/common"
export MUI_GATE3E_COMMON="$ROOT/openfoam/gate3e/common"
export MUI_GATE3F_COMMON="$ROOT/openfoam/gate3f/common"
export MUI_PROJECT_INCLUDE="$ROOT/include"
mkdir -p "$GATE3G_BUILD_DIR/openfoam"

for target in rhoCentralFoamGate3G dsmcFoamGate3G; do
    source_dir="$ROOT/openfoam/gate3g/$target"
    wclean "$source_dir" >/dev/null 2>&1 || true
    wmake "$source_dir"
done

for executable in rhoCentralFoamGate3G dsmcFoamGate3G; do
    if [[ ! -x "$GATE3G_BUILD_DIR/openfoam/$executable" ]]; then
        printf 'ERROR: Gate 3G executable was not built: %s\n' \
            "$executable" >&2
        exit 2
    fi
done
if [[ ! -x "$CORE_BUILD/dynamic_restart_scaling" ]]; then
    printf 'ERROR: Gate 3G scaling executable was not built.\n' >&2
    exit 2
fi
printf 'GATE3G_CONTINUUM_EXECUTABLE=%s\n' \
    "$GATE3G_BUILD_DIR/openfoam/rhoCentralFoamGate3G"
printf 'GATE3G_DSMC_EXECUTABLE=%s\n' \
    "$GATE3G_BUILD_DIR/openfoam/dsmcFoamGate3G"
printf 'GATE3G_SCALING_EXECUTABLE=%s\n' \
    "$CORE_BUILD/dynamic_restart_scaling"
