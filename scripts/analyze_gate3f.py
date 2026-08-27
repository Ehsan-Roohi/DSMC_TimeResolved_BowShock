#!/usr/bin/env python3
"""Analyze Gate 3F live coupling with dynamic DSMC particle ownership."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CONTINUUM_RE = re.compile(
    r"GATE3F_PASS role=continuum_live steps=(?P<steps>\d+) "
    r"windows=(?P<windows>\d+) full_rhoCentralFoam_time_advance=true "
    r"two_way_feedback_applied=true adaptive_sampling_surface=true "
    r"adaptive_layer_changes=(?P<changes>\d+) "
    r"min_feedback_scale=(?P<scale>[-+0-9.eE]+) "
    r"max_conservation_rel=(?P<conservation>[-+0-9.eE]+) "
    r"max_delta_U=(?P<du>[-+0-9.eE]+) "
    r"max_delta_T=(?P<dt>[-+0-9.eE]+)"
)
DSMC_RE = re.compile(
    r"GATE3F_PASS role=dsmc_live steps=(?P<steps>\d+) "
    r"windows=(?P<windows>\d+) final_parcels=(?P<parcels>\d+) "
    r"inserted=(?P<inserted>\d+) active_layer_changes=(?P<changes>\d+) "
    r"max_flux_checksum=(?P<checksum>[-+0-9.eE]+) "
    r"dynamic_activated_cells=(?P<activated>\d+) "
    r"deactivated_cells=(?P<deactivated>\d+) "
    r"seeded_parcels=(?P<seeded>\d+) "
    r"removed_parcels=(?P<removed>\d+) "
    r"retained_identities=(?P<retained>\d+) "
    r"inactive_parcels=(?P<inactive>\d+) "
    r"ownership_balance_error=(?P<balance>\d+) "
    r"max_overlap_z=(?P<overlap>[-+0-9.eE]+)"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace")
    if "GATE3F_FAIL" in text or "GATE3E_FAIL" in text or "GATE3C_FAIL" in text:
        raise ValueError("a Gate 3F dependency or live failure marker is present")
    continuum = CONTINUUM_RE.search(text)
    dsmc = DSMC_RE.search(text)
    if not continuum or not dsmc:
        raise ValueError("Gate 3F final PASS markers are incomplete")
    continuum_values = {
        key: float(value) for key, value in continuum.groupdict().items()
    }
    dsmc_values = {key: float(value) for key, value in dsmc.groupdict().items()}
    if int(continuum_values["steps"]) != 1000 or int(dsmc_values["steps"]) != 1000:
        raise ValueError("Gate 3F must complete exactly 1000 synchronized steps")
    if int(continuum_values["windows"]) != 5 or int(dsmc_values["windows"]) != 5:
        raise ValueError("Gate 3F must complete exactly five feedback windows")
    if int(continuum_values["changes"]) != int(dsmc_values["changes"]):
        raise ValueError("continuum and DSMC layer-change inventories differ")
    if continuum_values["conservation"] > 1.0e-12:
        raise ValueError("Gate 3F feedback conservation failed")
    if not 0.0 < continuum_values["scale"] <= 1.0:
        raise ValueError("invalid Gate 3F feedback scale")
    if continuum_values["du"] <= 0.0 or continuum_values["dt"] <= 0.0:
        raise ValueError("Gate 3F feedback did not change continuum state")
    for key in ("activated", "deactivated", "seeded", "removed", "retained"):
        if int(dsmc_values[key]) <= 0:
            raise ValueError(f"dynamic particle-domain event is missing: {key}")
    if int(dsmc_values["inactive"]) != 0 or int(dsmc_values["balance"]) != 0:
        raise ValueError("dynamic particle ownership is not exact")
    if dsmc_values["overlap"] > 1.0:
        raise ValueError("activated-cell state exceeds one sampling standard error")
    if dsmc_values["parcels"] <= 0 or dsmc_values["checksum"] <= 0.0:
        raise ValueError("Gate 3F physical DSMC feedback is empty")
    if len(re.findall(r"GATE3F_WINDOW role=continuum\b", text)) != 5:
        raise ValueError("Gate 3F continuum window inventory is incomplete")
    if len(re.findall(r"GATE3F_WINDOW role=dsmc\b", text)) != 5:
        raise ValueError("Gate 3F DSMC window inventory is incomplete")
    if "mpi://continuum/gate3f" not in text or "mpi://dsmc/gate3f" not in text:
        raise ValueError("Gate 3F MUI MPMD identifiers are missing")

    summary = {
        "gate": "3F-DYNAMIC-PARTICLE-DOMAIN",
        "status": "PASS",
        "transport": "MUI-MPMD synchronous bidirectional exchange",
        "continuum_solver": "derived OpenFOAM-v2312 rhoCentralFoam",
        "kinetic_solver": "derived OpenFOAM-v2312 dsmcFoam",
        "live_concurrent_openfoam_dsmc_completed": True,
        "continuum_and_dsmc_time_advanced_concurrently": True,
        "full_rhoCentralFoam_time_advance_completed": True,
        "physical_dsmc_wall_flux_sampled_live": True,
        "two_way_feedback_applied_to_continuum": True,
        "adaptive_sampling_surface_completed": True,
        "adaptive_particle_domain_completed": True,
        "mesh_topology_changed": False,
        "particle_ownership_boundary_moved_inside_fixed_validated_mesh": True,
        "synchronized_steps": 1000,
        "coupling_windows": 5,
        "samples_per_window": 40,
        "continuum_adaptive_layer_changes": int(continuum_values["changes"]),
        "dsmc_observed_layer_changes": int(dsmc_values["changes"]),
        "dynamic_activated_cells": int(dsmc_values["activated"]),
        "dynamic_deactivated_cells": int(dsmc_values["deactivated"]),
        "transition_seeded_parcels": int(dsmc_values["seeded"]),
        "removed_inactive_parcels": int(dsmc_values["removed"]),
        "retained_particle_identities_audited": int(dsmc_values["retained"]),
        "maximum_inactive_parcels": int(dsmc_values["inactive"]),
        "maximum_particle_ownership_balance_error": int(dsmc_values["balance"]),
        "maximum_activation_mismatch_standard_errors": dsmc_values["overlap"],
        "minimum_feedback_scale": continuum_values["scale"],
        "maximum_feedback_conservation_relative_error": continuum_values["conservation"],
        "maximum_velocity_change_m_per_s": continuum_values["du"],
        "maximum_temperature_change_K": continuum_values["dt"],
        "final_dsmc_parcels": int(dsmc_values["parcels"]),
        "inserted_dsmc_parcels": int(dsmc_values["inserted"]),
        "maximum_live_flux_checksum": dsmc_values["checksum"],
        "run_dir": args.run_dir,
        "log": str(args.log),
    }
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("GATE3F_DYNAMIC_DOMAIN_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
