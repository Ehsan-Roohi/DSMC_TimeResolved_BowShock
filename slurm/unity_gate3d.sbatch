#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3d
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=16G
#SBATCH --time=00:30:00
#SBATCH --output=reports/gate3d-%j.out
#SBATCH --error=reports/gate3d-%j.err

set -euo pipefail

ROOT=${GATE3D_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}}
if [[ ! -r "$ROOT/scripts/run_gate3d.sh" ]]; then
    printf 'ERROR: Gate 3D repository root is invalid: %s\n' "$ROOT" >&2
    exit 2
fi
cd "$ROOT"
bash "$ROOT/scripts/run_gate3d.sh"
