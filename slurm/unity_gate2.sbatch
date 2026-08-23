#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g2
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=00:30:00
#SBATCH --output=reports/gate2-%j.out
#SBATCH --error=reports/gate2-%j.err

set -euo pipefail

ROOT=${GATE2_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate2.sh" ]]; then
    printf 'ERROR: Gate 2 repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate2.sh"
