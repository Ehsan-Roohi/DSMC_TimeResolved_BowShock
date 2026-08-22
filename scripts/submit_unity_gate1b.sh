#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$ROOT/reports"

if ! command -v sbatch >/dev/null 2>&1; then
    printf 'ERROR: sbatch was not found. Run this script on a Unity login node.\n' >&2
    exit 2
fi

if [[ ! -f "$ROOT/reports/gate1a_summary.json" ]] \
    || ! grep -q '"status": "PASS"' "$ROOT/reports/gate1a_summary.json"; then
    printf 'ERROR: Gate 1A has not passed in this checkout.\n' >&2
    exit 2
fi

bash "$ROOT/scripts/prepare_mui.sh"

JOB_ID=$(sbatch --parsable --chdir="$ROOT" "$ROOT/slurm/unity_gate1b.sbatch")
printf 'GATE1B_JOB_ID=%s\n' "$JOB_ID"
printf 'WATCH=squeue -j %s\n' "$JOB_ID"
printf 'LOG=%s/reports/gate1b-%s.out\n' "$ROOT" "$JOB_ID"
