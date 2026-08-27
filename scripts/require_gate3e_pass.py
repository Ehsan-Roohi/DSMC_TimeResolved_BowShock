#!/usr/bin/env python3
"""Require the verified Gate 3E live concurrent result before Gate 3F."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3e_pass.py SUMMARY")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    required_true = (
        "live_concurrent_openfoam_dsmc_completed",
        "continuum_and_dsmc_time_advanced_concurrently",
        "full_rhoCentralFoam_time_advance_completed",
        "physical_dsmc_wall_flux_sampled_live",
        "two_way_feedback_applied_to_continuum",
        "adaptive_sampling_surface_completed",
    )
    valid = (
        data.get("gate") == "3E-LIVE-CONCURRENT-COUPLING"
        and data.get("status") == "PASS"
        and all(data.get(key) is True for key in required_true)
        and data.get("adaptive_particle_domain_completed") is False
        and data.get("synchronized_steps") == 1000
        and data.get("coupling_windows") == 5
        and data.get("samples_per_window") == 40
        and int(data.get("continuum_adaptive_layer_changes", 0)) > 0
        and int(data.get("dsmc_observed_layer_changes", 0)) > 0
        and float(data.get("minimum_feedback_scale", 0.0)) > 0.0
        and float(data.get("maximum_feedback_conservation_relative_error", 1.0))
        <= 1.0e-12
        and float(data.get("maximum_velocity_change_m_per_s", 0.0)) > 0.0
        and float(data.get("maximum_temperature_change_K", 0.0)) > 0.0
        and int(data.get("final_dsmc_parcels", 0)) > 0
        and float(data.get("maximum_live_flux_checksum", 0.0)) > 0.0
        and isinstance(data.get("run_dir"), str)
        and bool(data.get("run_dir"))
    )
    if not valid:
        raise SystemExit(f"Gate 3E prerequisite is not a verified PASS: {path}")
    print(f"GATE3E_PREREQUISITE=PASS artifact={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
