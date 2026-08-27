#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3e
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=reports/gate3e-%j.out
#SBATCH --error=reports/gate3e-%j.err

set -euo pipefail

ROOT=${GATE3E_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3e.sh" ]]; then
    printf 'ERROR: Gate 3E repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3e.sh"
