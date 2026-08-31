#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.."&&pwd);REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)};BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3n-$RUN_ID"};RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3n-$RUN_ID"}
[[ ! -e "$RUN_DIR" ]]||{ echo "ERROR: run directory exists" >&2;exit 2;};mkdir -p "$RUN_DIR" "$REPORT_DIR"
STAGE=startup;trap 'x=$?;((x==0))||echo "GATE3N_PIPELINE_FAIL stage=$STAGE status=$x" >&2' EXIT
source "$ROOT/scripts/load_openfoam_if_needed.sh"
PREREQ="$ROOT/docs/results/gate3m_unity_63809559.json";python3 "$ROOT/scripts/require_gate3m_pass.py" "$PREREQ"
GATE3M_RUN=$(python3 - "$PREREQ" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["run_dir"])
PY
)
CMP="$REPORT_DIR/gate3c_wall_comparison.csv";[[ -s "$CMP" && -d "$GATE3M_RUN/continuum" && -d "$GATE3M_RUN/hybrid" ]]||exit 2
STAGE=tests;(cd "$ROOT"&&python3 -m unittest -q tests.test_gate3n)
STAGE=build;BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3n.sh"
cp -a "$GATE3M_RUN/continuum" "$RUN_DIR/continuum";cp -a "$GATE3M_RUN/hybrid" "$RUN_DIR/hybrid"
STATE="$RUN_DIR/gate3n.state";cp "$GATE3M_RUN/gate3m.state" "$STATE"
read -r MAGIC STEP FACES < "$STATE";[[ "$MAGIC" == GATE3G_STATE_V1 && "$STEP" == 10000 && "$FACES" == 64 ]]||{ echo "ERROR: invalid restart state" >&2;exit 2;}
for c in continuum hybrid;do compgen -G "$RUN_DIR/$c/processor*" >/dev/null&&reconstructPar -case "$RUN_DIR/$c" -latestTime -newTimes >/dev/null||true;done
STAGE=decompose
for spec in continuum:rhoCentralFoamGate3N hybrid:dsmcFoamGate3N;do c=${spec%%:*};app=${spec##*:};ctl="$RUN_DIR/$c/system/controlDict";foamDictionary "$ctl" -entry application -set "$app";foamDictionary "$ctl" -entry startFrom -set latestTime;foamDictionary "$ctl" -entry endTime -set 1;foamDictionary "$ctl" -entry deltaT -set 1e-7;foamDictionary "$ctl" -entry writeControl -set timeStep;foamDictionary "$ctl" -entry writeInterval -set 2000;foamDictionary "$ctl" -entry purgeWrite -set 3;cp "$ROOT/cases/gate3i/decomposeParDict" "$RUN_DIR/$c/system/decomposeParDict";foamDictionary "$RUN_DIR/$c/system/decomposeParDict" -entry numberOfSubdomains -set 2;foamDictionary "$RUN_DIR/$c/system/decomposeParDict" -entry simpleCoeffs/n -set '(2 1 1)';decomposePar -case "$RUN_DIR/$c" -force >/dev/null;done
MPI=${MPI_LAUNCHER:-$(command -v mpirun)};export OMPI_MCA_pml=${OMPI_MCA_pml:-ob1}
for c in continuum hybrid;do "$MPI" -np 2 checkMesh -parallel -case "$RUN_DIR/$c" -constant >/dev/null;done
STAGE=kn_gl_live;LIVE="$REPORT_DIR/gate3n_live.log";HISTORY="$RUN_DIR/kn_gl_interface_history.csv"
echo 'GATE3N_LAYOUT continuum_ranks=2 dsmc_ranks=2 total_ranks=4 start_step=10000 stop_step=12000 steps=2000 windows=10 criterion=Kn_GL'|tee "$LIVE"
timeout --signal=TERM --kill-after=30 3600 "$MPI" -np 2 env GATE3G_COMPARISON="$CMP" GATE3G_CONTINUUM_URI=mpi://continuum/gate3n GATE3G_SEGMENT=gate3n GATE3G_START_STEP=10000 GATE3G_STOP_STEP=12000 GATE3G_STATE_FILE="$STATE" GATE3N_KNGL_HISTORY="$HISTORY" "$BUILD_DIR/openfoam/rhoCentralFoamGate3N" -parallel -world continuum -case "$RUN_DIR/continuum" : -np 2 env GATE3C_ROLE=live GATE3G_DSMC_URI=mpi://dsmc/gate3n GATE3G_SEGMENT=gate3n GATE3G_START_STEP=10000 GATE3G_STOP_STEP=12000 GATE3G_STATE_FILE="$STATE" "$BUILD_DIR/openfoam/dsmcFoamGate3N" -parallel -world dsmc -case "$RUN_DIR/hybrid" 2>&1|tee -a "$LIVE"
STAGE=reconstruct;reconstructPar -case "$RUN_DIR/continuum" -latestTime -newTimes >/dev/null;CT=$(foamListTimes -case "$RUN_DIR/continuum" -latestTime);FIELD="$RUN_DIR/continuum/$CT/KnGL";[[ -s "$FIELD" ]]||exit 2
STAGE=analysis;python3 "$ROOT/scripts/analyze_gate3n.py" --live "$LIVE" --history "$HISTORY" --field "$FIELD" --summary "$REPORT_DIR/gate3n_summary.json" --run-dir "$RUN_DIR"
echo "GATE3N_SUMMARY=$REPORT_DIR/gate3n_summary.json";echo "GATE3N_RUN_DIR=$RUN_DIR";STAGE=complete
