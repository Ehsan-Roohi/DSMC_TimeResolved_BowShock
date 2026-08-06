#!/usr/bin/env bash
set -euo pipefail
repo="Ehsan-Roohi/DSMC_TimeResolved_BowShock"
if command -v gh >/dev/null 2>&1; then
  gh repo create "$repo" --public --source . --remote origin --push
else
  echo "Create an empty public repository named DSMC_TimeResolved_BowShock, then run:"
  echo "git remote add origin https://github.com/$repo.git"
  echo "git push -u origin main"
fi
