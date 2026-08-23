#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate2"}

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

python3 "$ROOT/scripts/require_gate1c_pass.py" \
    "$ROOT/reports/gate1c_summary.json"

export GATE2_BUILD_DIR="$BUILD_DIR"
mkdir -p "$GATE2_BUILD_DIR/openfoam"
for target in gate2ContinuumIndicator gate2ParticleManager; do
    source_dir="$ROOT/openfoam/gate2/$target"
    wclean "$source_dir" >/dev/null 2>&1 || true
    wmake "$source_dir"
done

for executable in gate2ContinuumIndicator gate2ParticleManager; do
    if [[ ! -x "$GATE2_BUILD_DIR/openfoam/$executable" ]]; then
        printf 'ERROR: Gate 2 executable was not built: %s\n' "$executable" >&2
        exit 2
    fi
done
printf 'GATE2_INDICATOR_EXECUTABLE=%s\n' \
    "$GATE2_BUILD_DIR/openfoam/gate2ContinuumIndicator"
printf 'GATE2_PARTICLE_MANAGER=%s\n' \
    "$GATE2_BUILD_DIR/openfoam/gate2ParticleManager"
