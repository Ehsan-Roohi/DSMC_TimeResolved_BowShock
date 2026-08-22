#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MUI_COMMIT=b130c7a12aa8e7ac8d54e9188c4836342daed263
DEPS_DIR=${DEPS_DIR:-"$ROOT/_deps"}
MUI_SRC=${MUI_SRC:-"$DEPS_DIR/MUI"}
MUI_BUILD=${MUI_BUILD:-"$DEPS_DIR/MUI-build"}
MUI_PREFIX=${MUI_PREFIX:-"$DEPS_DIR/MUI-install"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate0"}
BUILD_JOBS=${BUILD_JOBS:-2}

for command_name in git cmake mpic++; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'ERROR: required command not found: %s\n' "$command_name" >&2
        exit 2
    fi
done

MUI_SRC="$MUI_SRC" DEPS_DIR="$DEPS_DIR" bash "$ROOT/scripts/prepare_mui.sh"

cmake -S "$MUI_SRC" -B "$MUI_BUILD" \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INSTALL_PREFIX="$MUI_PREFIX" \
    -DC_WRAPPER=OFF \
    -DFORTRAN_WRAPPER=OFF \
    -DPYTHON_WRAPPER=OFF
cmake --build "$MUI_BUILD" --target install --parallel "$BUILD_JOBS"

cmake -S "$ROOT" -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DMUI_DIR="$MUI_PREFIX/MUI-2.0.0/share/MUI-2.0.0/cmake" \
    -DBUILD_MUI_GATE0=ON \
    -DBUILD_CORE_TESTS=ON
cmake --build "$BUILD_DIR" --parallel "$BUILD_JOBS"
ctest --test-dir "$BUILD_DIR" --output-on-failure

printf 'GATE0_EXECUTABLE=%s\n' "$BUILD_DIR/mui_state_exchange"
