#!/usr/bin/env bash

# This file is sourced by run_gate0.sh. Keep module discovery recoverable so
# the report contains a useful error instead of failing on the first probe.

have_openfoam()
{
    command -v wmake >/dev/null 2>&1 \
        && command -v rhoCentralFoam >/dev/null 2>&1 \
        && command -v dsmcFoam >/dev/null 2>&1
}

have_mpi()
{
    command -v mpic++ >/dev/null 2>&1 \
        && command -v mpirun >/dev/null 2>&1
}

source_foam_bashrc()
{
    local bashrc=$1
    if [[ ! -r "$bashrc" ]]; then
        printf 'ERROR: OpenFOAM bashrc is not readable: %s\n' "$bashrc" >&2
        return 2
    fi

    # Older OpenFOAM bashrc files are not nounset-clean.
    set +u
    # shellcheck disable=SC1090
    source "$bashrc"
    set -u
    printf 'OPENFOAM_BASHRC_LOADED=%s\n' "$bashrc"
}

if have_openfoam && have_mpi; then
    return 0 2>/dev/null || exit 0
fi

if ! command -v module >/dev/null 2>&1; then
    for init_file in /etc/profile.d/modules.sh /usr/share/Modules/init/bash; do
        if [[ -r "$init_file" ]]; then
            # shellcheck disable=SC1090
            source "$init_file"
            break
        fi
    done
fi

if [[ -n "${OPENFOAM_BASHRC:-}" ]]; then
    if ! have_mpi && command -v module >/dev/null 2>&1; then
        mpi_module=${OPENMPI_MODULE:-openmpi/5.0.3}
        module load "$mpi_module"
        printf 'OPENMPI_MODULE_LOADED=%s\n' "$mpi_module"
    fi
    source_foam_bashrc "$OPENFOAM_BASHRC"
else
    if ! command -v module >/dev/null 2>&1; then
        printf 'ERROR: module command is unavailable and OPENFOAM_BASHRC was not supplied.\n' >&2
        return 2 2>/dev/null || exit 2
    fi

    foam_module=${OPENFOAM_MODULE:-openfoam/2312}

    if [[ -n "${OPENMPI_MODULE:-}" ]]; then
        module load "$OPENMPI_MODULE"
        printf 'OPENMPI_MODULE_LOADED=%s\n' "$OPENMPI_MODULE"
    fi

    if module load "$foam_module" >/dev/null 2>&1; then
        printf 'OPENFOAM_MODULE_LOADED=%s\n' "$foam_module"
    elif [[ -z "${OPENMPI_MODULE:-}" ]]; then
        loaded=false
        for mpi_module in openmpi/5.0.3 openmpi/4.1.6; do
            module purge >/dev/null 2>&1 || true
            if module load "$mpi_module" >/dev/null 2>&1 \
                && module load "$foam_module" >/dev/null 2>&1; then
                printf 'OPENMPI_MODULE_LOADED=%s\n' "$mpi_module"
                printf 'OPENFOAM_MODULE_LOADED=%s\n' "$foam_module"
                loaded=true
                break
            fi
        done
        if [[ "$loaded" != true ]]; then
            printf 'ERROR: unable to load %s with the supported Unity MPI modules.\n' "$foam_module" >&2
            module spider "$foam_module" 2>&1 | sed -n '1,160p' >&2 || true
            return 2 2>/dev/null || exit 2
        fi
    else
        printf 'ERROR: unable to load requested OpenFOAM module: %s\n' "$foam_module" >&2
        module spider "$foam_module" 2>&1 | sed -n '1,160p' >&2 || true
        return 2 2>/dev/null || exit 2
    fi

    if ! command -v wmake >/dev/null 2>&1 \
        && [[ -n "${FOAM_BASHRC:-}" && -r "${FOAM_BASHRC:-}" ]]; then
        source_foam_bashrc "$FOAM_BASHRC"
    fi
fi

if ! have_mpi && command -v module >/dev/null 2>&1; then
    mpi_module=${OPENMPI_MODULE:-openmpi/5.0.3}
    module load "$mpi_module"
    printf 'OPENMPI_MODULE_LOADED=%s\n' "$mpi_module"
fi

if ! have_openfoam; then
    printf 'ERROR: OpenFOAM loaded without the required wmake, rhoCentralFoam, and dsmcFoam commands.\n' >&2
    return 2 2>/dev/null || exit 2
fi

if ! have_mpi; then
    printf 'ERROR: MPI loaded without both mpic++ and mpirun.\n' >&2
    return 2 2>/dev/null || exit 2
fi
