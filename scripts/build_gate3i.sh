#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3i"}
python3 "$ROOT/scripts/require_gate3h_pass.py" \
    "$ROOT/reports/gate3h_summary.json"
cmake -S "$ROOT" -B "$BUILD_DIR" \
    -DCMAKE_BUILD_TYPE=Release \
    -DBUILD_MUI_GATE0=OFF \
    -DBUILD_MUI_GATE3I=ON \
    -DBUILD_CORE_TESTS=ON
cmake --build "$BUILD_DIR" --parallel 2
ctest --test-dir "$BUILD_DIR" --output-on-failure
printf 'GATE3I_MUI_PROBE=%s\n' "$BUILD_DIR/mui_domain_decomposition_probe"
