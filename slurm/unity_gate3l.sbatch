#!/usr/bin/env bash
#SBATCH --job-name=mui-of-g3l
#SBATCH --partition=cpu
#SBATCH --nodes=1
#SBATCH --ntasks=8
#SBATCH --cpus-per-task=1
#SBATCH --mem=32G
#SBATCH --time=01:00:00
#SBATCH --output=reports/gate3l-%j.out
#SBATCH --error=reports/gate3l-%j.err
set -euo pipefail
ROOT=${GATE3L_ROOT:-${SLURM_SUBMIT_DIR:-$PWD}};cd "$ROOT";bash "$ROOT/scripts/run_gate3l.sh"
