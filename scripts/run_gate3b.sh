#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3b"}
RUN_ID=${SLURM_JOB_ID:-manual-$$}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3b-$RUN_ID"}
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE3B_PILOT_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f "$REPORT_DIR/gate3b_pilot_summary.json"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"

STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3a_pass.py" \
    "$REPORT_DIR/gate3a_summary.json"

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate3b
)

STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3b.sh"
EXE="$BUILD_DIR/mui_moving_cylinder_flux"
MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 3B pilot runner.\n' >&2
    exit 127
fi

run_segment()
{
    local resolution=$1
    local mode=$2
    local input_state=$3
    local output_state=$4
    local log=$5
    local interface_name="gate3b_${resolution}_${mode}"
    timeout --signal=TERM --kill-after=30 300 \
        "$MPI_LAUNCHER" \
        -np 1 "$EXE" "mpi://dsmc/$interface_name" \
            dsmc "$mode" "$input_state" "$output_state" "$resolution" \
        : \
        -np 1 "$EXE" "mpi://continuum/$interface_name" \
            continuum "$mode" "$input_state" "$output_state" "$resolution" \
        2>&1 | tee "$log"
}

STAGE=resolution_audit
for resolution in coarse medium fine; do
    state="$RUN_DIR/${resolution}-continuous.state"
    log="$REPORT_DIR/gate3b_${resolution}_continuous.log"
    run_segment "$resolution" continuous - "$state" "$log"
    grep -q "GATE3B_PILOT_PASS role=dsmc mode=continuous resolution=$resolution" "$log"
    grep -q "GATE3B_PILOT_PASS role=continuum mode=continuous resolution=$resolution" "$log"
    grep -q 'window=0 .*statistically_resolved=false relaxation_applied=false' "$log"
done

STAGE=restart_audit
CHECKPOINT_STATE="$RUN_DIR/medium-checkpoint.state"
RESUMED_STATE="$RUN_DIR/medium-resumed.state"
FRESH_LOG="$REPORT_DIR/gate3b_medium_fresh.log"
RESTART_LOG="$REPORT_DIR/gate3b_medium_restart.log"
run_segment medium fresh - "$CHECKPOINT_STATE" "$FRESH_LOG"
run_segment medium restart "$CHECKPOINT_STATE" "$RESUMED_STATE" "$RESTART_LOG"
grep -q 'GATE3B_PILOT_PASS role=continuum mode=fresh resolution=medium' "$FRESH_LOG"
grep -q 'GATE3B_PILOT_PASS role=continuum mode=restart resolution=medium' "$RESTART_LOG"
if ! cmp -s "$RUN_DIR/medium-continuous.state" "$RESUMED_STATE"; then
    printf 'ERROR: Gate 3B pilot continuous and restarted states differ.\n' >&2
    exit 2
fi

SUMMARY="$REPORT_DIR/gate3b_pilot_summary.json"
STAGE=analysis
python3 - "$REPORT_DIR" "$RUN_DIR" "$SUMMARY" <<'PY'
import json
import math
import pathlib
import re
import sys

report_dir = pathlib.Path(sys.argv[1])
run_dir = pathlib.Path(sys.argv[2])
summary = pathlib.Path(sys.argv[3])
logs = sorted(report_dir.glob("gate3b_*_*.log"))
if len(logs) != 5:
    raise SystemExit(f"expected five Gate 3B pilot logs, found {len(logs)}")

raw = []
mapped = []
relaxed = []
moving = []
continuous_resolutions = set()
activated = 0
deactivated = 0
for path in logs:
    text = path.read_text(encoding="utf-8", errors="replace")
    if "GATE3B_PILOT_FAIL" in text:
        raise SystemExit(f"failure marker found in {path}")
    raw.extend(float(x) for x in re.findall(r"raw_rbf_conservation_rel=([^\s]+)", text))
    mapped.extend(float(x) for x in re.findall(r"(?<!raw_rbf_)mapped_conservation_rel=([^\s]+)", text))
    relaxed.extend(float(x) for x in re.findall(r"relaxed_conservation_rel=([^\s]+)", text))
    moving.extend(float(x) for x in re.findall(r"moving_boundary_conservation_rel=([^\s]+)", text))
    match = re.search(
        r"GATE3B_PILOT_PASS role=continuum mode=continuous resolution=(\w+).*?"
        r"activated_layers=(\d+) deactivated_layers=(\d+)",
        text,
    )
    if match:
        continuous_resolutions.add(match.group(1))
        activated += int(match.group(2))
        deactivated += int(match.group(3))

metrics = raw + mapped + relaxed + moving
if not metrics or not all(math.isfinite(value) and value >= 0.0 for value in metrics):
    raise SystemExit("Gate 3B pilot metrics are absent, negative, or non-finite")
if continuous_resolutions != {"coarse", "medium", "fine"}:
    raise SystemExit("Gate 3B pilot resolution audit is incomplete")
if activated <= 0 or deactivated <= 0:
    raise SystemExit("Gate 3B pilot did not exercise both interface directions")
if max(raw) > 0.2:
    raise SystemExit("Gate 3B pilot raw RBF defect exceeds 0.2")
if max(mapped + relaxed + moving) > 1.0e-8:
    raise SystemExit("Gate 3B pilot conservation tolerance exceeded")

continuous = run_dir / "medium-continuous.state"
resumed = run_dir / "medium-resumed.state"
if continuous.read_bytes() != resumed.read_bytes():
    raise SystemExit("Gate 3B pilot restart differs from continuous state")

data = {
    "gate": "3B-PILOT",
    "status": "PASS",
    "scope": "moving-cylinder-interface-conservation-and-resolution-pilot",
    "transport": "MUI-MPMD",
    "geometry": "moving-semicylindrical-interface",
    "resolutions": ["coarse", "medium", "fine"],
    "source_faces": [12, 18, 24],
    "target_faces": [16, 24, 32],
    "windows": 5,
    "activated_layer_events": activated,
    "deactivated_layer_events": deactivated,
    "maximum_raw_rbf_conservation_relative_error": max(raw),
    "maximum_allowed_raw_rbf_conservation_relative_error": 0.2,
    "maximum_mapped_conservation_relative_error": max(mapped),
    "maximum_relaxed_conservation_relative_error": max(relaxed),
    "maximum_moving_boundary_conservation_relative_error": max(moving),
    "conservation_tolerance": 1.0e-8,
    "restart_matches_continuous_byte_for_byte": True,
    "full_cylinder_physical_validation_completed": False,
    "parallel_scaling_completed": False,
    "run_dir": str(run_dir),
}
summary.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print(json.dumps(data, indent=2))
PY

printf 'GATE3B_PILOT_STATUS=PASS\n'
printf 'GATE3B_RUN_DIR=%s\n' "$RUN_DIR"
printf 'GATE3B_PILOT_SUMMARY=%s\n' "$SUMMARY"
STAGE=complete
