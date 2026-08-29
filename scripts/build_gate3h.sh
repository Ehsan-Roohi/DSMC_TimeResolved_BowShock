#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3h"}
python3 "$ROOT/scripts/require_gate3g_pass.py" \
    "$ROOT/reports/gate3g_summary.json"
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3g.sh"
printf 'GATE3H_CONTINUUM_EXECUTABLE=%s\n' \
    "$BUILD_DIR/openfoam/rhoCentralFoamGate3G"
printf 'GATE3H_DSMC_EXECUTABLE=%s\n' \
    "$BUILD_DIR/openfoam/dsmcFoamGate3G"
