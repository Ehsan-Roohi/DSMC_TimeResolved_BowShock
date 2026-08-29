#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPS_DIR=${DEPS_DIR:-"$ROOT/_deps"}
MUI_SRC=${MUI_SRC:-"$DEPS_DIR/MUI"}
MUI_BUILD=${MUI_BUILD:-"$DEPS_DIR/MUI-build"}
MUI_PREFIX=${MUI_PREFIX:-"$DEPS_DIR/MUI-install"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3i"}
BUILD_JOBS=${BUILD_JOBS:-2}
MUI_CONFIG="$MUI_PREFIX/MUI-2.0.0/share/MUI-2.0.0/cmake"

for command_name in cmake mpic++; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'ERROR: required command not found: %s\n' "$command_name" >&2
        exit 2
    fi
done

python3 "$ROOT/scripts/require_gate3h_pass.py" \
    "$ROOT/reports/gate3h_summary.json"
MUI_SRC="$MUI_SRC" DEPS_DIR="$DEPS_DIR" \
    bash "$ROOT/scripts/prepare_mui.sh"
if [[ ! -r "$MUI_CONFIG/MUIConfig.cmake" ]]; then
    cmake -S "$MUI_SRC" -B "$MUI_BUILD" \
        -DCMAKE_BUILD_TYPE=Release \
        -DCMAKE_CXX_COMPILER="$(command -v mpic++)" \
        -DCMAKE_INSTALL_PREFIX="$MUI_PREFIX" \
        -DC_WRAPPER=OFF \
        -DFORTRAN_WRAPPER=OFF \
        -DPYTHON_WRAPPER=OFF
    cmake --build "$MUI_BUILD" --target install --parallel "$BUILD_JOBS"
fi
cmake -S "$ROOT" -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_CXX_COMPILER="$(command -v mpic++)" \
    -DMUI_DIR="$MUI_CONFIG" \
    -DBUILD_MUI_GATE0=OFF \
    -DBUILD_MUI_GATE3I=ON \
    -DBUILD_CORE_TESTS=ON
cmake --build "$BUILD_DIR" --parallel "$BUILD_JOBS"
ctest --test-dir "$BUILD_DIR" --output-on-failure
printf 'GATE3I_MUI_PROBE=%s\n' "$BUILD_DIR/mui_domain_decomposition_probe"
