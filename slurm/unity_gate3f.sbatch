#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3f
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:45:00
#SBATCH --output=reports/gate3f-%j.out
#SBATCH --error=reports/gate3f-%j.err

set -euo pipefail

ROOT=${GATE3F_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3f.sh" ]]; then
    printf 'ERROR: Gate 3F repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3f.sh"
