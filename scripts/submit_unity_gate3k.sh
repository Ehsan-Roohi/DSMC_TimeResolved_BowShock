#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
mkdir -p "$ROOT/reports"
command -v sbatch >/dev/null 2>&1 || { echo "ERROR: sbatch not found" >&2; exit 2; }
ACTIVE=$(squeue -h -u "${USER:?USER is not set}" -o '%A|%j|%T' |
    awk -F'|' '$2=="mui-of-g3k" && ($3=="PENDING"||$3=="RUNNING"||$3=="COMPLETING"){print $1;exit}')
[[ -z "$ACTIVE" ]] || { echo "ERROR: Gate 3K job $ACTIVE is already active" >&2; exit 2; }
python3 "$ROOT/scripts/require_gate3j_pass.py" "$ROOT/docs/results/gate3j_unity_63797532.json"
[[ -s "$ROOT/reports/gate3i_summary.json" ]] || { echo "ERROR: Gate 3I summary missing" >&2; exit 2; }
[[ -s "$ROOT/reports/gate3c_wall_comparison.csv" ]] || { echo "ERROR: Gate 3C comparison missing" >&2; exit 2; }
bash "$ROOT/scripts/prepare_mui.sh"
JOB_ID=$(sbatch --parsable --chdir="$ROOT" --export=ALL,GATE3K_ROOT="$ROOT" "$ROOT/slurm/unity_gate3k.sbatch")
printf 'GATE3K_JOB_ID=%s\nWATCH=squeue -j %s\nLOG=%s/reports/gate3k-%s.out\n' "$JOB_ID" "$JOB_ID" "$ROOT" "$JOB_ID"
