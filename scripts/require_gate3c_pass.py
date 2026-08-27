#!/usr/bin/env python3
"""Reject Gate 3D unless the physical Gate 3C preflight truly passed."""

from __future__ import annotations

import json
import math
import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3c_pass.py gate3c_physical_summary.json")
    path = pathlib.Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"Gate 3C physical PASS artifact is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("gate") != "3C-PHYSICAL-PREFLIGHT" or data.get("status") != "PASS":
        raise SystemExit("Gate 3C artifact does not report physical-preflight PASS")
    if data.get("openfoam_version") != "v2312":
        raise SystemExit("Gate 3C did not use the pinned OpenFOAM version")
    if data.get("coupling") != "one-way-fixed-radius-continuum-to-dsmc-via-MUI":
        raise SystemExit("Gate 3C coupling identity is unexpected")
    if data.get("interface_selected_before_reference") is not True:
        raise SystemExit("Gate 3C interface was not selected before its reference")
    if data.get("full_dsmc_executed_after_hybrid") is not True:
        raise SystemExit("Gate 3C did not execute the full DSMC reference last")
    if int(data.get("wall_faces", 0)) != 64 or int(data.get("samples_per_face_used", 0)) < 200:
        raise SystemExit("Gate 3C physical sampling inventory is incomplete")
    if data.get("heat_flux_pass") is not True or data.get("drag_pass") is not True:
        raise SystemExit("Gate 3C wall-observable validation failed")

    q_error = float(data.get("heat_flux_normalized_l2", math.inf))
    q_limit = float(data.get("heat_flux_acceptance_threshold", -math.inf))
    d_error = float(data.get("drag_density_normalized_l2", math.inf))
    d_limit = float(data.get("drag_acceptance_threshold", -math.inf))
    total_drag_error = float(data.get("total_drag_relative_error", math.inf))
    metrics = [q_error, q_limit, d_error, d_limit, total_drag_error]
    if not all(math.isfinite(value) and value >= 0.0 for value in metrics):
        raise SystemExit("Gate 3C physical metrics are invalid")
    if q_error > q_limit or d_error > d_limit or total_drag_error > 0.05:
        raise SystemExit("Gate 3C physical errors exceed their declared limits")
    if any(
        data.get(key) is not False
        for key in (
            "two_way_flux_applied_to_continuum",
            "adaptive_interface_completed",
            "parallel_scaling_completed",
        )
    ):
        raise SystemExit("Gate 3C scope flags were altered before Gate 3D")
    print(f"GATE3C_PHYSICAL_PREREQUISITE=PASS artifact={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
