#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.."&&pwd);mkdir -p "$ROOT/reports"
A=$(squeue -h -u "$USER" -n mui-of-g3n -o '%A'|head -n1);[[ -z "$A" ]]||{ echo "ERROR: Gate3N already active $A";exit 2;}
python3 "$ROOT/scripts/require_gate3m_pass.py" "$ROOT/docs/results/gate3m_unity_63809559.json"
bash "$ROOT/scripts/prepare_mui.sh"
J=$(sbatch --parsable --chdir="$ROOT" --export=ALL,GATE3N_ROOT="$ROOT" "$ROOT/slurm/unity_gate3n.sbatch")
echo "GATE3N_JOB_ID=$J";echo "WATCH=squeue -j $J";echo "LOG=$ROOT/reports/gate3n-$J.out"
