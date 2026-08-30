#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.."&&pwd);REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)};BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3m-$RUN_ID"};RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3m-$RUN_ID"}
[[ ! -e "$RUN_DIR" ]]||{ echo "ERROR: run directory exists" >&2;exit 2; };mkdir -p "$RUN_DIR" "$REPORT_DIR"
STAGE=startup;trap 'x=$?;((x==0))||echo "GATE3M_PIPELINE_FAIL stage=$STAGE status=$x" >&2' EXIT
source "$ROOT/scripts/load_openfoam_if_needed.sh"
STAGE=prerequisite;python3 "$ROOT/scripts/require_gate3l_pass.py" "$ROOT/docs/results/gate3l_unity_63806295.json"
python3 "$ROOT/scripts/require_gate3i_pass.py" "$REPORT_DIR/gate3i_summary.json"
CMP="$REPORT_DIR/gate3c_wall_comparison.csv";[[ -s "$CMP" ]]||exit 2
STAGE=static_tests;(cd "$ROOT"&&python3 -m unittest -q tests.test_gate3m)
STAGE=build;BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3j.sh"
SRC=$(python3 - "$REPORT_DIR/gate3i_summary.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["run_dir"]+"/ranks_1")
PY
)
cp -a "$SRC/continuum" "$RUN_DIR/continuum";cp -a "$SRC/hybrid" "$RUN_DIR/hybrid"
for spec in continuum:rhoCentralFoamGate3J hybrid:dsmcFoamGate3J;do
 case_name=${spec%%:*};app=${spec##*:};ctl="$RUN_DIR/$case_name/system/controlDict"
 foamDictionary "$ctl" -entry application -set "$app";foamDictionary "$ctl" -entry startFrom -set latestTime
 foamDictionary "$ctl" -entry endTime -set 1;foamDictionary "$ctl" -entry deltaT -set 1e-7
 foamDictionary "$ctl" -entry writeControl -set timeStep;foamDictionary "$ctl" -entry writeInterval -set 10000;foamDictionary "$ctl" -entry purgeWrite -set 2
 cp "$ROOT/cases/gate3i/decomposeParDict" "$RUN_DIR/$case_name/system/decomposeParDict"
 foamDictionary "$RUN_DIR/$case_name/system/decomposeParDict" -entry numberOfSubdomains -set 2
 foamDictionary "$RUN_DIR/$case_name/system/decomposeParDict" -entry simpleCoeffs/n -set '(2 1 1)'
 decomposePar -case "$RUN_DIR/$case_name" -force >/dev/null
done
MPI=${MPI_LAUNCHER:-$(command -v mpirun)};export OMPI_MCA_pml=${OMPI_MCA_pml:-ob1}
for case_name in continuum hybrid;do "$MPI" -np 2 checkMesh -parallel -case "$RUN_DIR/$case_name" -constant >/dev/null;done
STAGE=long_live;LIVE="$REPORT_DIR/gate3m_live.log";STATE="$RUN_DIR/gate3m.state"
echo 'GATE3M_LAYOUT continuum_ranks=2 dsmc_ranks=2 total_ranks=4 steps=10000 windows=50'|tee "$LIVE"
timeout --signal=TERM --kill-after=30 7200 "$MPI" \
 -np 2 env GATE3G_COMPARISON="$CMP" GATE3G_CONTINUUM_URI=mpi://continuum/gate3m GATE3G_SEGMENT=gate3m GATE3G_START_STEP=0 GATE3G_STOP_STEP=10000 \
  "$BUILD_DIR/openfoam/rhoCentralFoamGate3J" -parallel -world continuum -case "$RUN_DIR/continuum" \
 : -np 2 env GATE3C_ROLE=live GATE3G_DSMC_URI=mpi://dsmc/gate3m GATE3G_SEGMENT=gate3m GATE3G_START_STEP=0 GATE3G_STOP_STEP=10000 GATE3G_STATE_FILE="$STATE" \
  "$BUILD_DIR/openfoam/dsmcFoamGate3J" -parallel -world dsmc -case "$RUN_DIR/hybrid" 2>&1|tee -a "$LIVE"
STAGE=analysis;python3 "$ROOT/scripts/analyze_gate3m.py" --live "$LIVE" --summary "$REPORT_DIR/gate3m_summary.json" --run-dir "$RUN_DIR"
echo "GATE3M_SUMMARY=$REPORT_DIR/gate3m_summary.json";echo "GATE3M_RUN_DIR=$RUN_DIR";STAGE=complete
