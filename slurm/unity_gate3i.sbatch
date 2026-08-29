#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3i
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=00:30:00
#SBATCH --output=reports/gate3i-%j.out
#SBATCH --error=reports/gate3i-%j.err

set -euo pipefail

ROOT=${GATE3I_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3i.sh" ]]; then
    printf 'ERROR: Gate 3I repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3i.sh"
