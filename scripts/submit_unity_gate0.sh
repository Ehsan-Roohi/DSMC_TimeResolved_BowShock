#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$ROOT/reports"

if ! command -v sbatch >/dev/null 2>&1; then
    printf 'ERROR: sbatch was not found. Run this script on a Unity login node.\n' >&2
    exit 2
fi

# Acquire the pinned source on the login node. Compute nodes can then build
# without requiring outbound network access.
bash "$ROOT/scripts/prepare_mui.sh"

JOB_ID=$(sbatch --parsable --chdir="$ROOT" "$ROOT/slurm/unity_gate0.sbatch")
printf 'GATE0_JOB_ID=%s\n' "$JOB_ID"
printf 'WATCH=squeue -j %s\n' "$JOB_ID"
printf 'LOG=%s/reports/gate0-%s.out\n' "$ROOT" "$JOB_ID"
