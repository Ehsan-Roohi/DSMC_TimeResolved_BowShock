#!/usr/bin/env bash

# This file is sourced. Do not enable `set -e` here because module discovery
# varies across clusters and absence of a module must remain a probe result.

if command -v foamVersion >/dev/null 2>&1; then
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

if [[ -n "${OPENFOAM_MODULE:-}" ]] && command -v module >/dev/null 2>&1; then
    module load "$OPENFOAM_MODULE"
fi
