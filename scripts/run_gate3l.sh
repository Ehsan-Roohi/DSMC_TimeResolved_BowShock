#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd); REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}; BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3l-$RUN_ID"}; RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3l-$RUN_ID"}
[[ ! -e "$RUN_DIR" ]] || { echo "ERROR: run directory exists" >&2;exit 2; };mkdir -p "$RUN_DIR" "$REPORT_DIR"
STAGE=startup;trap 'x=$?;((x==0))||echo "GATE3L_PIPELINE_FAIL stage=$STAGE status=$x" >&2' EXIT
source "$ROOT/scripts/load_openfoam_if_needed.sh"
STAGE=prerequisite;python3 "$ROOT/scripts/require_gate3k_pass.py" "$ROOT/docs/results/gate3k_unity_63804488.json"
python3 "$ROOT/scripts/require_gate3i_pass.py" "$REPORT_DIR/gate3i_summary.json"
CMP="$REPORT_DIR/gate3c_wall_comparison.csv";[[ -s "$CMP" ]]||exit 2
STAGE=static_tests;(cd "$ROOT"&&python3 -m unittest -q tests.test_gate3l)
STAGE=build;BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3j.sh"
SRC=$(python3 - "$REPORT_DIR/gate3i_summary.json" <<'PY'
import json,sys
print(json.load(open(sys.argv[1]))["run_dir"]+"/ranks_1")
PY
)
MPI=${MPI_LAUNCHER:-$(command -v mpirun)}
for ranks in 1 2 4;do
 C="$RUN_DIR/ranks_$ranks";mkdir -p "$C";cp -a "$SRC/continuum" "$C/continuum";cp -a "$SRC/hybrid" "$C/hybrid"
 for spec in continuum:rhoCentralFoamGate3J hybrid:dsmcFoamGate3J;do
  case_name=${spec%%:*};app=${spec##*:};ctl="$C/$case_name/system/controlDict"
  foamDictionary "$ctl" -entry application -set "$app";foamDictionary "$ctl" -entry startFrom -set latestTime
  foamDictionary "$ctl" -entry endTime -set 1;foamDictionary "$ctl" -entry deltaT -set 1e-7
  foamDictionary "$ctl" -entry writeControl -set timeStep;foamDictionary "$ctl" -entry writeInterval -set 1000;foamDictionary "$ctl" -entry purgeWrite -set 2
 done
 if ((ranks>1));then
  for case_name in continuum hybrid;do
   cp "$ROOT/cases/gate3i/decomposeParDict" "$C/$case_name/system/decomposeParDict"
   foamDictionary "$C/$case_name/system/decomposeParDict" -entry numberOfSubdomains -set "$ranks"
   foamDictionary "$C/$case_name/system/decomposeParDict" -entry simpleCoeffs/n -set "($ranks 1 1)"
   decomposePar -case "$C/$case_name" -force >/dev/null
   "$MPI" -np "$ranks" checkMesh -parallel -case "$C/$case_name" -constant >/dev/null
  done
 fi
done
run_layout(){
 local r=$1 c="$RUN_DIR/ranks_$1" log="$REPORT_DIR/gate3l_ranks_$1.log" session="gate3l_ranks_$1" par=()
 ((r==1))||par=(-parallel)
 echo "GATE3L_LAYOUT ranks_per_solver=$r total_ranks=$((2*r)) steps=1000" | tee "$log"
 local begin=$(date +%s%N)
 timeout --signal=TERM --kill-after=30 2400 "$MPI" \
  -np "$r" env GATE3G_COMPARISON="$CMP" GATE3G_CONTINUUM_URI="mpi://continuum/$session" GATE3G_SEGMENT="scaling_$r" GATE3G_START_STEP=0 GATE3G_STOP_STEP=1000 \
   "$BUILD_DIR/openfoam/rhoCentralFoamGate3J" "${par[@]}" -case "$c/continuum" \
  : -np "$r" env GATE3C_ROLE=live GATE3G_DSMC_URI="mpi://dsmc/$session" GATE3G_SEGMENT="scaling_$r" GATE3G_START_STEP=0 GATE3G_STOP_STEP=1000 GATE3G_STATE_FILE="$c/gate3l.state" \
   "$BUILD_DIR/openfoam/dsmcFoamGate3J" "${par[@]}" -case "$c/hybrid" 2>&1|tee -a "$log"
 local end=$(date +%s%N);local wall=$(awk -v s="$begin" -v e="$end" 'BEGIN{printf "%.6f",(e-s)/1e9}')
 echo "GATE3L_TIMING ranks_per_solver=$r total_ranks=$((2*r)) wall_seconds=$wall"|tee -a "$log"
 grep -q 'GATE3J_PASS role=continuum_distributed' "$log";grep -q 'GATE3J_PASS role=dsmc_distributed' "$log"
}
for ranks in 1 2 4;do STAGE="scaling_$ranks";run_layout "$ranks";done
STAGE=analysis;python3 "$ROOT/scripts/analyze_gate3l.py" --logs "$REPORT_DIR/gate3l_ranks_1.log" "$REPORT_DIR/gate3l_ranks_2.log" "$REPORT_DIR/gate3l_ranks_4.log" --summary "$REPORT_DIR/gate3l_summary.json" --run-dir "$RUN_DIR"
echo "GATE3L_SUMMARY=$REPORT_DIR/gate3l_summary.json";echo "GATE3L_RUN_DIR=$RUN_DIR";STAGE=complete
