#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
MUI_COMMIT=b130c7a12aa8e7ac8d54e9188c4836342daed263
DEPS_DIR=${DEPS_DIR:-"$ROOT/_deps"}
MUI_SRC=${MUI_SRC:-"$DEPS_DIR/MUI"}

if ! command -v git >/dev/null 2>&1; then
    printf 'ERROR: git is required to acquire the pinned MUI source.\n' >&2
    exit 2
fi

mkdir -p "$DEPS_DIR"
if [[ ! -d "$MUI_SRC/.git" ]]; then
    git clone https://github.com/MxUI/MUI.git "$MUI_SRC"
fi

if ! git -C "$MUI_SRC" cat-file -e "$MUI_COMMIT^{commit}" 2>/dev/null; then
    git -C "$MUI_SRC" fetch --depth 1 origin "$MUI_COMMIT"
fi
git -C "$MUI_SRC" checkout --detach "$MUI_COMMIT"

printf 'MUI_SOURCE=%s\n' "$MUI_SRC"
printf 'MUI_COMMIT=%s\n' "$MUI_COMMIT"
