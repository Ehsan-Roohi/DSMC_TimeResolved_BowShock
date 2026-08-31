#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.."&&pwd)
MUI_PREFIX=${MUI_PREFIX:-"$ROOT/_deps/MUI-install"};MUI_INCLUDE_DIR_VALUE="$MUI_PREFIX/MUI-2.0.0/include"
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3n"}
source "$ROOT/scripts/load_openfoam_if_needed.sh"
python3 "$ROOT/scripts/require_gate3m_pass.py" "$ROOT/docs/results/gate3m_unity_63809559.json"
for c in cmake mpic++ wmake;do command -v "$c" >/dev/null||{ echo "ERROR: missing $c" >&2;exit 2;};done
[[ -r "$MUI_INCLUDE_DIR_VALUE/mui.h" ]]||{ echo "ERROR: MUI headers missing" >&2;exit 2;}
if [[ -z "${MPI_ARCH_PATH:-}" ]];then MPI_ARCH_PATH=$(mpic++ --showme:prefix);export MPI_ARCH_PATH;fi
cmake -S "$ROOT" -B "$BUILD_DIR/core" -DBUILD_MUI_GATE0=OFF -DBUILD_CORE_TESTS=ON
cmake --build "$BUILD_DIR/core" --parallel 2;ctest --test-dir "$BUILD_DIR/core" --output-on-failure
export GATE3N_BUILD_DIR="$BUILD_DIR" MUI_INCLUDE_DIR="$MUI_INCLUDE_DIR_VALUE"
export MUI_GATE1B_COMMON="$ROOT/openfoam/gate1b/common" MUI_GATE3C_COMMON="$ROOT/openfoam/gate3c/common"
export MUI_GATE3E_COMMON="$ROOT/openfoam/gate3e/common" MUI_GATE3F_COMMON="$ROOT/openfoam/gate3f/common"
export MUI_PROJECT_INCLUDE="$ROOT/include";mkdir -p "$BUILD_DIR/openfoam"
for t in rhoCentralFoamGate3N dsmcFoamGate3N;do wclean "$ROOT/openfoam/gate3n/$t" >/dev/null 2>&1||true;wmake "$ROOT/openfoam/gate3n/$t";[[ -x "$BUILD_DIR/openfoam/$t" ]]||exit 2;done
echo "GATE3N_BUILD=PASS"
