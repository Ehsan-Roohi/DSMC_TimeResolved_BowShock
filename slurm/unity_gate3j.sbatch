#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3j
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=reports/gate3j-%j.out
#SBATCH --error=reports/gate3j-%j.err

set -euo pipefail

ROOT=${GATE3J_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3j.sh" ]]; then
    printf 'ERROR: Gate 3J repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3j.sh"
