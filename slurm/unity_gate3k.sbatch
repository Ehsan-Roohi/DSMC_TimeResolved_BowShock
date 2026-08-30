#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3k
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=reports/gate3k-%j.out
#SBATCH --error=reports/gate3k-%j.err

set -euo pipefail
ROOT=${GATE3K_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
[[ -r "$ROOT/scripts/run_gate3k.sh" ]] || { echo "ERROR: invalid Gate 3K root: $ROOT" >&2; exit 2; }
cd "$ROOT"
bash "$ROOT/scripts/run_gate3k.sh"
