#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3n
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=4
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=02:00:00
#SBATCH --output=reports/gate3n-%j.out
#SBATCH --error=reports/gate3n-%j.err
set -euo pipefail
ROOT=${GATE3N_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}};cd "$ROOT";bash "$ROOT/scripts/run_gate3n.sh"
