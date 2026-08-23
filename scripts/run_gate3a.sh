#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3a"}
RUN_ID=${SLURM_JOB_ID:-manual-$$}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3a-$RUN_ID"}
mkdir -p "$REPORT_DIR" "$RUN_DIR"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
python3 "$ROOT/scripts/require_gate2_pass.py" \
    "$REPORT_DIR/gate2_summary.json"
bash "$ROOT/scripts/build_gate3a.sh"

EXE="$BUILD_DIR/mui_conservative_flux"
MPI_LAUNCHER=$(command -v mpirun)
CONTINUOUS_STATE="$RUN_DIR/continuous.state"
CHECKPOINT_STATE="$RUN_DIR/checkpoint.state"
RESUMED_STATE="$RUN_DIR/resumed.state"
CONTINUOUS_LOG="$REPORT_DIR/gate3a_continuous.log"
FRESH_LOG="$REPORT_DIR/gate3a_fresh.log"
RESTART_LOG="$REPORT_DIR/gate3a_restart.log"
SUMMARY="$REPORT_DIR/gate3a_summary.json"

run_segment()
{
    local mode=$1
    local input_state=$2
    local output_state=$3
    local log=$4
    "$MPI_LAUNCHER" \
        -np 1 "$EXE" mpi://dsmc/gate3a dsmc "$mode" "$input_state" "$output_state" \
        : \
        -np 1 "$EXE" mpi://continuum/gate3a continuum "$mode" "$input_state" "$output_state" \
        2>&1 | tee "$log"
}

run_segment continuous - "$CONTINUOUS_STATE" "$CONTINUOUS_LOG"
run_segment fresh - "$CHECKPOINT_STATE" "$FRESH_LOG"
run_segment restart "$CHECKPOINT_STATE" "$RESUMED_STATE" "$RESTART_LOG"

grep -q 'GATE3A_PASS role=dsmc mode=continuous' "$CONTINUOUS_LOG"
grep -q 'GATE3A_PASS role=continuum mode=continuous' "$CONTINUOUS_LOG"
grep -q 'window=0 .*statistically_resolved=false relaxation_applied=false' "$CONTINUOUS_LOG"
grep -q 'GATE3A_PASS role=continuum mode=fresh' "$FRESH_LOG"
grep -q 'GATE3A_PASS role=continuum mode=restart' "$RESTART_LOG"
if ! cmp -s "$CONTINUOUS_STATE" "$RESUMED_STATE"; then
    printf 'ERROR: continuous and restarted conservative flux states differ.\n' >&2
    exit 2
fi

python3 - \
    "$CONTINUOUS_LOG" "$FRESH_LOG" "$RESTART_LOG" \
    "$CONTINUOUS_STATE" "$CHECKPOINT_STATE" "$RESUMED_STATE" \
    "$RUN_DIR" "$SUMMARY" <<'PY'
import json
import math
import pathlib
import re
import sys

logs = [pathlib.Path(p) for p in sys.argv[1:4]]
states = [pathlib.Path(p) for p in sys.argv[4:7]]
run_dir = pathlib.Path(sys.argv[7])
summary = pathlib.Path(sys.argv[8])
mapped = []
relaxed = []
for path in logs:
    text = path.read_text(encoding="utf-8", errors="replace")
    mapped.extend(float(x) for x in re.findall(r"mapped_conservation_rel=([^\s]+)", text))
    relaxed.extend(float(x) for x in re.findall(r"relaxed_conservation_rel=([^\s]+)", text))
if not mapped or not relaxed or not all(math.isfinite(x) for x in mapped + relaxed):
    raise SystemExit("Gate 3A conservation metrics are absent or non-finite")
if states[0].read_bytes() != states[2].read_bytes():
    raise SystemExit("Gate 3A restart state differs from continuous state")
data = {
    "gate": "3A",
    "status": "PASS",
    "transport": "MUI-MPMD",
    "mapping": "conservative-RBF-integrated-face-flux",
    "flux_components": ["mass", "momentum_x", "momentum_y", "momentum_z", "energy"],
    "source_blocks": 9,
    "continuum_faces": 16,
    "windows": 3,
    "minimum_resolved_samples": 64,
    "maximum_resolved_relative_standard_error": 0.05,
    "unresolved_window_skipped": True,
    "maximum_mapped_conservation_relative_error": max(mapped),
    "maximum_relaxed_conservation_relative_error": max(relaxed),
    "conservation_tolerance": 1.0e-8,
    "restart_matches_continuous_byte_for_byte": True,
    "run_dir": str(run_dir),
    "checkpoint": str(states[1]),
}
summary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(json.dumps(data, indent=2))
PY

printf 'GATE3A_STATUS=PASS\n'
printf 'GATE3A_RUN_DIR=%s\n' "$RUN_DIR"
printf 'GATE3A_SUMMARY=%s\n' "$SUMMARY"
