#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
RUN_ID=${SLURM_JOB_ID:-manual-$(date -u +%Y%m%dT%H%M%SZ)}
BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3i-$RUN_ID"}
RUN_DIR=${RUN_DIR:-"$ROOT/run/gate3i-$RUN_ID"}
if [[ -e "$RUN_DIR" ]]; then
    printf 'ERROR: refusing to overwrite Gate 3I run directory: %s\n' \
        "$RUN_DIR" >&2
    exit 2
fi
mkdir -p "$REPORT_DIR" "$RUN_DIR"
STAGE=startup
trap '
    status=$?
    if (( status != 0 )); then
        printf "GATE3I_PIPELINE_FAIL stage=%s status=%d\n" "$STAGE" "$status" >&2
    fi
' EXIT
rm -f "$REPORT_DIR/gate3i_summary.json" \
    "$REPORT_DIR/gate3i_ranks_1.log" \
    "$REPORT_DIR/gate3i_ranks_2.log" \
    "$REPORT_DIR/gate3i_ranks_4.log"

# shellcheck disable=SC1091
source "$ROOT/scripts/load_openfoam_if_needed.sh"
GATE3H_SUMMARY="$REPORT_DIR/gate3h_summary.json"
STAGE=prerequisite
python3 "$ROOT/scripts/require_gate3h_pass.py" "$GATE3H_SUMMARY"

STAGE=static_tests
(
    cd "$ROOT"
    python3 -m unittest -q tests.test_gate3i
)
STAGE=build
BUILD_DIR="$BUILD_DIR" bash "$ROOT/scripts/build_gate3i.sh"

GATE3H_RUN_DIR=$(python3 - "$GATE3H_SUMMARY" <<'PY'
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))
value = data.get("run_dir")
if not isinstance(value, str) or not value:
    raise SystemExit("Gate 3H summary has no run_dir")
print(value)
PY
)
case "$GATE3H_RUN_DIR" in
    "$ROOT"/run/gate3h-*) ;;
    *)
        printf 'ERROR: Gate 3H run directory is outside the repository.\n' >&2
        exit 2
        ;;
esac
SOURCE_CASE="$GATE3H_RUN_DIR/scaling_1/replica_0"
for case_name in continuum hybrid; do
    if [[ ! -d "$SOURCE_CASE/$case_name" ]]; then
        printf 'ERROR: Gate 3H source case is missing: %s\n' \
            "$SOURCE_CASE/$case_name" >&2
        exit 2
    fi
done

MPI_LAUNCHER=${MPI_LAUNCHER:-$(command -v mpirun || true)}
if [[ -z "$MPI_LAUNCHER" || ! -x "$MPI_LAUNCHER" ]]; then
    printf 'ERROR: mpirun is unavailable in the Gate 3I runner.\n' >&2
    exit 127
fi

run_rank_pair() {
    local ranks=$1
    local case_root="$RUN_DIR/ranks_$ranks"
    local log_file="$REPORT_DIR/gate3i_ranks_$ranks.log"
    mkdir -p "$case_root"
    cp -a "$SOURCE_CASE/continuum" "$case_root/continuum"
    cp -a "$SOURCE_CASE/hybrid" "$case_root/hybrid"
    : >"$log_file"

    local role case_name case_dir role_log processor_dirs
    for role in continuum dsmc; do
        case_name=continuum
        [[ "$role" == dsmc ]] && case_name=hybrid
        case_dir="$case_root/$case_name"
        role_log="$case_root/checkMesh_${role}.log"
        if (( ranks == 1 )); then
            checkMesh -case "$case_dir" -latestTime >"$role_log" 2>&1
            processor_dirs=0
        else
            cp "$ROOT/cases/gate3i/decomposeParDict" \
                "$case_dir/system/decomposeParDict"
            foamDictionary "$case_dir/system/decomposeParDict" \
                -entry numberOfSubdomains -set "$ranks"
            decomposePar -case "$case_dir" -force -latestTime \
                >>"$role_log" 2>&1
            "$MPI_LAUNCHER" -np "$ranks" checkMesh -parallel \
                -case "$case_dir" -latestTime >>"$role_log" 2>&1
            processor_dirs=$(find "$case_dir" -maxdepth 1 -type d \
                -name 'processor[0-9]*' | wc -l)
        fi
        cat "$role_log" >>"$log_file"
        if ! grep -q 'Mesh OK\.' "$role_log"; then
            printf 'GATE3I_FAIL reason=checkMesh role=%s ranks=%s\n' \
                "$role" "$ranks" | tee -a "$log_file"
            return 1
        fi
        if (( processor_dirs != (ranks == 1 ? 0 : ranks) )); then
            printf 'GATE3I_FAIL reason=processor_inventory role=%s ranks=%s actual=%s\n' \
                "$role" "$ranks" "$processor_dirs" | tee -a "$log_file"
            return 1
        fi
        printf 'GATE3I_DECOMPOSITION role=%s ranks=%s processor_dirs=%s mesh_ok=true\n' \
            "$role" "$ranks" "$processor_dirs" | tee -a "$log_file"
    done

    local session="gate3i_${ranks}"
    timeout --signal=TERM --kill-after=15 180 \
        "$MPI_LAUNCHER" \
        -np "$ranks" "$BUILD_DIR/mui_domain_decomposition_probe" \
            "mpi://continuum/$session" continuum "$ranks" \
        : \
        -np "$ranks" "$BUILD_DIR/mui_domain_decomposition_probe" \
            "mpi://dsmc/$session" dsmc "$ranks" \
        2>&1 | tee -a "$log_file"
}

for ranks in 1 2 4; do
    STAGE="decomposition_and_transport_${ranks}"
    run_rank_pair "$ranks"
done

SUMMARY="$REPORT_DIR/gate3i_summary.json"
STAGE=analysis
python3 "$ROOT/scripts/analyze_gate3i.py" \
    --logs "$REPORT_DIR/gate3i_ranks_1.log" \
           "$REPORT_DIR/gate3i_ranks_2.log" \
           "$REPORT_DIR/gate3i_ranks_4.log" \
    --summary "$SUMMARY" \
    --run-dir "$RUN_DIR"
printf 'GATE3I_SUMMARY=%s\n' "$SUMMARY"
printf 'GATE3I_RUN_DIR=%s\n' "$RUN_DIR"
STAGE=complete
