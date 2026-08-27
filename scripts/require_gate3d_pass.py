#!/usr/bin/env python3
"""Require the verified Gate 3D physical-feedback result before Gate 3E."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3d_pass.py SUMMARY")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    required_true = (
        "two_way_flux_applied_to_continuum",
        "adaptive_interface_completed",
        "restart_matches_continuous_byte_for_byte",
        "parallel_scaling_completed",
    )
    valid = (
        data.get("gate") == "3D-PHYSICAL-FEEDBACK-REPLAY"
        and data.get("status") == "PASS"
        and all(data.get(key) is True for key in required_true)
        and data.get("live_concurrent_openfoam_dsmc_completed") is False
        and data.get("scaling_rank_counts") == [1, 2, 4]
        and float(data.get("feedback_conservation_relative_error", 1.0)) <= 1.0e-12
        and float(data.get("maximum_raw_transport_conservation_relative_error", 1.0))
        <= 1.0e-10
        and float(data.get("maximum_projected_conservation_relative_error", 1.0))
        <= 1.0e-12
        and float(data.get("maximum_relaxed_conservation_relative_error", 1.0))
        <= 1.0e-12
        and float(data.get("scaling_numerical_invariance_relative_error", 1.0))
        <= 1.0e-12
    )
    if not valid:
        raise SystemExit(f"Gate 3D prerequisite is not a verified PASS: {path}")
    print(f"GATE3D_PREREQUISITE=PASS artifact={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
