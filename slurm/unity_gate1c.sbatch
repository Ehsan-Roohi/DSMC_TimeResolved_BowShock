#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g1c
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=2
#SBATCH --cpus-per-task=1
#SBATCH --mem=12G
#SBATCH --time=00:40:00
#SBATCH --output=reports/gate1c-%j.out
#SBATCH --error=reports/gate1c-%j.err

set -euo pipefail

ROOT=${SLURM_SUBMIT_DIR:?SLURM_SUBMIT_DIR is not set}
bash "$ROOT/scripts/run_gate1c.sh"
