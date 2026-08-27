#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPS_DIR=${DEPS_DIR:-"$ROOT/_deps"}
MUI_SRC=${MUI_SRC:-"$DEPS_DIR/MUI"}
MUI_BUILD=${MUI_BUILD:-"$DEPS_DIR/MUI-build"}
MUI_PREFIX=${MUI_PREFIX:-"$DEPS_DIR/MUI-install"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3d"}
BUILD_JOBS=${BUILD_JOBS:-2}
MUI_CONFIG="$MUI_PREFIX/MUI-2.0.0/share/MUI-2.0.0/cmake"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
python3 "$ROOT/scripts/require_gate3c_pass.py" \
    "$ROOT/reports/gate3c_physical_summary.json"
for command_name in cmake mpic++ wmake; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'ERROR: required Gate 3D build command not found: %s\n' \
            "$command_name" >&2
        exit 2
    fi
done

MUI_SRC="$MUI_SRC" DEPS_DIR="$DEPS_DIR" bash "$ROOT/scripts/prepare_mui.sh"
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
    -DBUILD_MUI_GATE1A=OFF \
    -DBUILD_MUI_GATE3A=OFF \
    -DBUILD_MUI_GATE3B=OFF \
    -DBUILD_MUI_GATE3D=ON \
    -DBUILD_CORE_TESTS=ON
cmake --build "$BUILD_DIR" --parallel "$BUILD_JOBS"
ctest --test-dir "$BUILD_DIR" --output-on-failure

export GATE3D_BUILD_DIR="$BUILD_DIR"
mkdir -p "$GATE3D_BUILD_DIR/openfoam"
FEEDBACK_SOURCE="$ROOT/openfoam/gate3d/gate3dContinuumFeedback"
wclean "$FEEDBACK_SOURCE" >/dev/null 2>&1 || true
wmake "$FEEDBACK_SOURCE"

for executable in \
    "$BUILD_DIR/mui_physical_feedback" \
    "$BUILD_DIR/physical_feedback_scaling" \
    "$BUILD_DIR/openfoam/gate3dContinuumFeedback"; do
    if [[ ! -x "$executable" ]]; then
        printf 'ERROR: Gate 3D executable was not built: %s\n' \
            "$executable" >&2
        exit 2
    fi
done
printf 'GATE3D_MUI_EXECUTABLE=%s\n' "$BUILD_DIR/mui_physical_feedback"
printf 'GATE3D_SCALING_EXECUTABLE=%s\n' "$BUILD_DIR/physical_feedback_scaling"
printf 'GATE3D_OPENFOAM_FEEDBACK=%s\n' \
    "$BUILD_DIR/openfoam/gate3dContinuumFeedback"
