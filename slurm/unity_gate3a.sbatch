#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3a
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=6G
#SBATCH --time=00:20:00
#SBATCH --output=reports/gate3a-%j.out
#SBATCH --error=reports/gate3a-%j.err

set -euo pipefail

ROOT=${GATE3A_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3a.sh" ]]; then
    printf 'ERROR: Gate 3A repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3a.sh"
