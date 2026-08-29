#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$ROOT/reports"
if ! command -v sbatch >/dev/null 2>&1; then
    printf 'ERROR: sbatch was not found. Run this script on a Unity login node.\n' >&2
    exit 2
fi
ACTIVE_JOB=$(
    squeue -h -u "${USER:?USER is not set}" -o '%A|%j|%T' \
    | awk -F'|' \
        '$2 == "mui-of-g3i" && ($3 == "PENDING" || $3 == "RUNNING" || $3 == "COMPLETING") {print $1; exit}'
)
if [[ -n "$ACTIVE_JOB" ]]; then
    printf 'ERROR: Gate 3I job %s is already active; refusing duplicate submission.\n' \
        "$ACTIVE_JOB" >&2
    exit 2
fi
python3 "$ROOT/scripts/require_gate3h_pass.py" \
    "$ROOT/reports/gate3h_summary.json"
bash "$ROOT/scripts/prepare_mui.sh"

JOB_ID=$(sbatch \
    --parsable \
    --chdir="$ROOT" \
    --export=ALL,GATE3I_ROOT="$ROOT" \
    "$ROOT/slurm/unity_gate3i.sbatch")
printf 'GATE3I_JOB_ID=%s\n' "$JOB_ID"
printf 'WATCH=squeue -j %s\n' "$JOB_ID"
printf 'LOG=%s/reports/gate3i-%s.out\n' "$ROOT" "$JOB_ID"
