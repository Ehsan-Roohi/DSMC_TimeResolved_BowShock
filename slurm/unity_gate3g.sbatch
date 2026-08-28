#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3g
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=01:00:00
#SBATCH --output=reports/gate3g-%j.out
#SBATCH --error=reports/gate3g-%j.err

set -euo pipefail

ROOT=${GATE3G_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3g.sh" ]]; then
    printf 'ERROR: Gate 3G repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3g.sh"
