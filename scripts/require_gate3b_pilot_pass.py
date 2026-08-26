#!/usr/bin/env python3
"""Reject a Gate 3C submission unless the Unity Gate 3B pilot truly passed."""

from __future__ import annotations

import json
import math
import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3b_pilot_pass.py gate3b_pilot_summary.json")
    path = pathlib.Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"Gate 3B pilot PASS artifact is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("gate") != "3B-PILOT" or data.get("status") != "PASS":
        raise SystemExit("Gate 3B pilot artifact does not report PASS")
    if data.get("transport") != "MUI-MPMD":
        raise SystemExit("Gate 3B pilot did not prove MUI MPMD transport")
    if set(data.get("resolutions", [])) != {"coarse", "medium", "fine"}:
        raise SystemExit("Gate 3B pilot resolution audit is incomplete")
    if int(data.get("activated_layer_events", 0)) <= 0:
        raise SystemExit("Gate 3B pilot did not activate interface layers")
    if int(data.get("deactivated_layer_events", 0)) <= 0:
        raise SystemExit("Gate 3B pilot did not deactivate interface layers")
    if data.get("restart_matches_continuous_byte_for_byte") is not True:
        raise SystemExit("Gate 3B pilot restart determinism failed")

    raw = float(data.get("maximum_raw_rbf_conservation_relative_error", math.inf))
    raw_limit = float(
        data.get("maximum_allowed_raw_rbf_conservation_relative_error", -math.inf)
    )
    tolerance = float(data.get("conservation_tolerance", -math.inf))
    projected = [
        float(data.get("maximum_mapped_conservation_relative_error", math.inf)),
        float(data.get("maximum_relaxed_conservation_relative_error", math.inf)),
        float(data.get("maximum_moving_boundary_conservation_relative_error", math.inf)),
    ]
    if not all(math.isfinite(value) for value in [raw, raw_limit, tolerance, *projected]):
        raise SystemExit("Gate 3B pilot conservation metrics are non-finite")
    if not 0.0 <= raw <= raw_limit or raw_limit <= 0.0:
        raise SystemExit("Gate 3B pilot raw RBF defect exceeds its declared limit")
    if tolerance <= 0.0 or any(value < 0.0 or value > tolerance for value in projected):
        raise SystemExit("Gate 3B pilot projected conservation failed")
    print(f"GATE3B_PILOT_PREREQUISITE=PASS artifact={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
