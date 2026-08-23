#!/usr/bin/env python3
"""Fail unless the supplied file is a complete Gate 1C PASS artifact."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate1c_pass.py SUMMARY.json")
    path = Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"Gate 1C summary is missing: {path}")
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SystemExit(f"Gate 1C summary is unreadable: {error}") from error
    required = {
        "gate": "1C",
        "status": "PASS",
        "interface_selected_before_reference": True,
        "full_dsmc_executed_after_hybrid": True,
        "heat_flux_pass": True,
        "shear_pass": True,
    }
    failures = [
        f"{key}={record.get(key)!r} (expected {expected!r})"
        for key, expected in required.items()
        if record.get(key) != expected
    ]
    if failures:
        raise SystemExit("invalid Gate 1C PASS artifact: " + "; ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
