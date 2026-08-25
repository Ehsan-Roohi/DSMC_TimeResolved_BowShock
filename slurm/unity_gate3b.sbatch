#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3b
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:20:00
#SBATCH --output=reports/gate3b-%j.out
#SBATCH --error=reports/gate3b-%j.err

set -euo pipefail

ROOT=${GATE3B_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3b.sh" ]]; then
    printf 'ERROR: Gate 3B repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3b.sh"
