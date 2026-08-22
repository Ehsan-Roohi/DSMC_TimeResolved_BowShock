#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MUI_PREFIX=${MUI_PREFIX:-"$ROOT/_deps/MUI-install"}
MUI_CMAKE_DIR="$MUI_PREFIX/MUI-2.0.0/share/MUI-2.0.0/cmake"
MUI_INCLUDE_DIR_VALUE="$MUI_PREFIX/MUI-2.0.0/include"
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate1a"}
BUILD_JOBS=${BUILD_JOBS:-2}

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

if [[ ! -f "$ROOT/reports/gate0_summary.json" ]] \
    || ! grep -q '"status": "PASS"' "$ROOT/reports/gate0_summary.json"; then
    printf 'ERROR: Gate 0 PASS artifact is required before Gate 1A.\n' >&2
    exit 2
fi

if [[ ! -f "$MUI_CMAKE_DIR/MUIConfig.cmake" ]]; then
    printf 'ERROR: pinned MUI installation from Gate 0 was not found.\n' >&2
    exit 2
fi

cmake -S "$ROOT" -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_COMPILER="$(command -v mpic++)" \
    -DMUI_DIR="$MUI_CMAKE_DIR" \
    -DBUILD_MUI_GATE0=OFF \
    -DBUILD_MUI_GATE1A=ON \
    -DBUILD_CORE_TESTS=ON
cmake --build "$BUILD_DIR" --parallel "$BUILD_JOBS"
ctest --test-dir "$BUILD_DIR" --output-on-failure

export MUI_GATE1_BIN="$BUILD_DIR/openfoam"
export MUI_INCLUDE_DIR="$MUI_INCLUDE_DIR_VALUE"
export MUIFOAM_INCLUDE_DIR="$ROOT/include"
mkdir -p "$MUI_GATE1_BIN"

wclean "$ROOT/openfoam/gate1a/muiOpenFoamApiProbe" >/dev/null 2>&1 || true
wmake "$ROOT/openfoam/gate1a/muiOpenFoamApiProbe"
"$MUI_GATE1_BIN/muiOpenFoamApiProbe"

printf 'GATE1A_EXECUTABLE=%s\n' "$BUILD_DIR/mui_fixed_interface"
printf 'GATE1A_OPENFOAM_PROBE=%s\n' "$MUI_GATE1_BIN/muiOpenFoamApiProbe"
