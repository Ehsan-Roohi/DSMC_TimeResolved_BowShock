#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.."&&pwd);mkdir -p "$ROOT/reports"
A=$(squeue -h -u "$USER" -n mui-of-g3m -o '%A'|head -n1);[[ -z "$A" ]]||{ echo "ERROR: Gate3M already active $A";exit 2; }
python3 "$ROOT/scripts/require_gate3l_pass.py" "$ROOT/docs/results/gate3l_unity_63806295.json"
bash "$ROOT/scripts/prepare_mui.sh"
J=$(sbatch --parsable --chdir="$ROOT" --export=ALL,GATE3M_ROOT="$ROOT" "$ROOT/slurm/unity_gate3m.sbatch")
echo "GATE3M_JOB_ID=$J";echo "WATCH=squeue -j $J";echo "LOG=$ROOT/reports/gate3m-$J.out"
