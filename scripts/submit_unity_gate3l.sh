#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.."&&pwd);mkdir -p "$ROOT/reports"
A=$(squeue -h -u "$USER" -n mui-of-g3l -o '%A'|head -n1);[[ -z "$A" ]]||{ echo "ERROR: Gate3L already active $A";exit 2; }
python3 "$ROOT/scripts/require_gate3k_pass.py" "$ROOT/docs/results/gate3k_unity_63804488.json"
bash "$ROOT/scripts/prepare_mui.sh"
J=$(sbatch --parsable --chdir="$ROOT" --export=ALL,GATE3L_ROOT="$ROOT" "$ROOT/slurm/unity_gate3l.sbatch")
echo "GATE3L_JOB_ID=$J";echo "WATCH=squeue -j $J";echo "LOG=$ROOT/reports/gate3l-$J.out"
