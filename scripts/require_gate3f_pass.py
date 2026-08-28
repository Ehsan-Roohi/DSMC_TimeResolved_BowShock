#!/usr/bin/env python3
"""Require the verified Gate 3F dynamic particle-domain result."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3f_pass.py SUMMARY")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    required_true = (
        "live_concurrent_openfoam_dsmc_completed",
        "continuum_and_dsmc_time_advanced_concurrently",
        "full_rhoCentralFoam_time_advance_completed",
        "physical_dsmc_wall_flux_sampled_live",
        "two_way_feedback_applied_to_continuum",
        "adaptive_sampling_surface_completed",
        "adaptive_particle_domain_completed",
        "particle_ownership_boundary_moved_inside_fixed_validated_mesh",
    )
    valid = (
        data.get("gate") == "3F-DYNAMIC-PARTICLE-DOMAIN"
        and data.get("status") == "PASS"
        and all(data.get(key) is True for key in required_true)
        and data.get("mesh_topology_changed") is False
        and data.get("synchronized_steps") == 1000
        and data.get("coupling_windows") == 5
        and data.get("samples_per_window") == 40
        and int(data.get("dynamic_activated_cells", 0)) > 0
        and int(data.get("dynamic_deactivated_cells", 0)) > 0
        and int(data.get("transition_seeded_parcels", 0)) > 0
        and int(data.get("removed_inactive_parcels", 0)) > 0
        and int(data.get("retained_particle_identities_audited", 0)) > 0
        and int(data.get("maximum_inactive_parcels", -1)) == 0
        and int(data.get("maximum_particle_ownership_balance_error", -1)) == 0
        and float(data.get("maximum_activation_mismatch_standard_errors", 2.0))
        <= 1.0
        and float(data.get("maximum_feedback_conservation_relative_error", 1.0))
        <= 1.0e-12
        and isinstance(data.get("run_dir"), str)
        and bool(data.get("run_dir"))
    )
    if not valid:
        raise SystemExit(f"Gate 3F prerequisite is not a verified PASS: {path}")
    print(f"GATE3F_PREREQUISITE=PASS artifact={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
