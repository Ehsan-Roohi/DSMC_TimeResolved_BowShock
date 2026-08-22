#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g0
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=4G
#SBATCH --time=00:15:00
#SBATCH --output=reports/gate0-%j.out
#SBATCH --error=reports/gate0-%j.err

set -euo pipefail

ROOT=${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is not set}

# Preserve a pre-loaded OpenFOAM module. If OpenFOAM is not already loaded,
# the probe records the missing environment instead of guessing a module.
bash "$ROOT/scripts/run_gate0.sh"
