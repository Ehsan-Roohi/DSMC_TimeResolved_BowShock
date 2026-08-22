#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g1b
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=8G
#SBATCH --time=00:20:00
#SBATCH --output=reports/gate1b-%j.out
#SBATCH --error=reports/gate1b-%j.err

set -euo pipefail

ROOT=${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is not set}
bash "$ROOT/scripts/run_gate1b.sh"
