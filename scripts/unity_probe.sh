#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
REPORT_DIR=${REPORT_DIR:-"$ROOT/reports"}
mkdir -p "$REPORT_DIR"
REPORT="$REPORT_DIR/unity_preflight.txt"

command_path()
{
    local name=$1
    if command -v "$name" >/dev/null 2>&1; then
        command -v "$name"
    else
        printf '%s\n' NOT_FOUND
    fi
}

first_source_match()
{
    local pattern=$1
    if [[ -n "${WM_PROJECT_DIR:-}" && -d "${WM_PROJECT_DIR:-}" ]]; then
        find "$WM_PROJECT_DIR/applications" -type f -path "$pattern" -print 2>/dev/null \
            | head -n 5
    else
        printf '%s\n' WM_PROJECT_DIR_NOT_SET
    fi
}

{
    printf 'probe_schema=1\n'
    printf 'timestamp_utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf 'hostname=%s\n' "$(hostname)"
    printf 'slurm_job_id=%s\n' "${SLURM_JOB_ID:-NOT_IN_SLURM}"
    printf 'slurm_ntasks=%s\n' "${SLURM_NTASKS:-UNSET}"
    printf 'wm_project=%s\n' "${WM_PROJECT:-UNSET}"
    printf 'wm_project_version=%s\n' "${WM_PROJECT_VERSION:-UNSET}"
    printf 'wm_project_dir=%s\n' "${WM_PROJECT_DIR:-UNSET}"
    printf 'foam_src=%s\n' "${FOAM_SRC:-UNSET}"
    printf 'foam_appbin=%s\n' "${FOAM_APPBIN:-UNSET}"
    printf 'foam_user_appbin=%s\n' "${FOAM_USER_APPBIN:-UNSET}"
    printf 'foam_version_command=%s\n' "$(command_path foamVersion)"
    if command -v foamVersion >/dev/null 2>&1; then
        printf 'foam_version_output=%s\n' "$(foamVersion 2>&1 | tr '\n' ' ')"
    fi
    printf 'rhoCentralFoam=%s\n' "$(command_path rhoCentralFoam)"
    printf 'dsmcFoam=%s\n' "$(command_path dsmcFoam)"
    printf 'dsmcInitialise=%s\n' "$(command_path dsmcInitialise)"
    printf 'foamRun=%s\n' "$(command_path foamRun)"
    printf 'wmake=%s\n' "$(command_path wmake)"
    printf 'mpicxx=%s\n' "$(command_path mpic++)"
    printf 'mpirun=%s\n' "$(command_path mpirun)"
    if command -v mpic++ >/dev/null 2>&1; then
        printf 'mpicxx_version=%s\n' "$(mpic++ --version 2>&1 | head -n 1)"
        printf 'mpicxx_show=%s\n' "$(mpic++ -show 2>&1 | head -n 1 || true)"
    fi
    if command -v mpirun >/dev/null 2>&1; then
        printf 'mpirun_version=%s\n' "$(mpirun --version 2>&1 | head -n 1)"
    fi
    printf 'cmake=%s\n' "$(command_path cmake)"
    if command -v cmake >/dev/null 2>&1; then
        printf 'cmake_version=%s\n' "$(cmake --version | head -n 1)"
    fi
    printf 'cxx=%s\n' "${CXX:-UNSET}"
    printf 'available_openfoam_modules_begin\n'
    if command -v module >/dev/null 2>&1; then
        module -t avail openfoam 2>&1 | sed -n '1,40p' || true
    else
        printf 'MODULE_COMMAND_NOT_AVAILABLE\n'
    fi
    printf 'available_openfoam_modules_end\n'
    printf 'rhoCentralFoam_sources_begin\n'
    first_source_match '*rhoCentralFoam*'
    printf 'rhoCentralFoam_sources_end\n'
    printf 'dsmcFoam_sources_begin\n'
    first_source_match '*dsmcFoam*'
    printf 'dsmcFoam_sources_end\n'
    printf 'shockFluid_sources_begin\n'
    first_source_match '*shockFluid*'
    printf 'shockFluid_sources_end\n'
} | tee "$REPORT"

printf 'PREFLIGHT_REPORT=%s\n' "$REPORT"
