#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3h
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=reports/gate3h-%j.out
#SBATCH --error=reports/gate3h-%j.err

set -euo pipefail

ROOT=${GATE3H_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3h.sh" ]]; then
    printf 'ERROR: Gate 3H repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3h.sh"
