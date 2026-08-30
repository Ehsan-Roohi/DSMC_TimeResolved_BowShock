#!/usr/bin/env python3
"""Analyze live spatially distributed OpenFOAM/MUI/DSMC evidence."""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path


def key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def one_marker(text: str, prefix: str, role: str) -> dict[str, str]:
    markers = [
        key_values(line.strip())
        for line in text.splitlines()
        if line.strip().startswith(prefix) and f"role={role}" in line
    ]
    if len(markers) != 1:
        raise ValueError(f"expected one {prefix.strip()} marker for {role}")
    return markers[0]


def analyze(live_path: Path, decomposition_path: Path, run_dir: str) -> dict[str, object]:
    live = live_path.read_text(encoding="utf-8", errors="replace")
    decomposition = decomposition_path.read_text(encoding="utf-8", errors="replace")
    if "GATE3J_FAIL" in live or "GATE3J_PIPELINE_FAIL" in live:
        raise ValueError("Gate 3J failure marker is present")
    if "mpi://continuum/gate3j" not in live or "mpi://dsmc/gate3j" not in live:
        raise ValueError("distributed MUI application inventory is incomplete")
    if (
        "GATE3J_LAYOUT continuum_ranks=2 dsmc_ranks=2 total_ranks=4 worlds=2"
        not in live
    ):
        raise ValueError("Gate 3J MPI layout marker is missing")

    expected_decomposition = {
        "GATE3J_DECOMPOSITION role=continuum spatial_ranks=2 fields=true mesh_ok=true",
        "GATE3J_DECOMPOSITION role=dsmc spatial_ranks=2 fields=true mesh_ok=true",
    }
    if not expected_decomposition.issubset(set(decomposition.splitlines())):
        raise ValueError("full-field decomposition evidence is incomplete")

    continuum = one_marker(live, "GATE3G_PASS ", "continuum_live")
    dsmc = one_marker(live, "GATE3G_PASS ", "dsmc_live")
    distributed_continuum = one_marker(
        live, "GATE3J_PASS ", "continuum_distributed"
    )
    distributed_dsmc = one_marker(live, "GATE3J_PASS ", "dsmc_distributed")
    for marker in (continuum, dsmc):
        if (
            marker.get("segment") != "gate3j"
            or int(marker["start_step"]) != 0
            or int(marker["stop_step"]) != 200
            or int(marker["steps"]) != 200
            or int(marker["first_step"]) != 1
            or int(marker["last_step"]) != 200
            or int(marker["windows"]) != 1
        ):
            raise ValueError("distributed live step inventory is invalid")
    if continuum.get("full_rhoCentralFoam_time_advance") != "true":
        raise ValueError("continuum solver did not advance")
    if continuum.get("two_way_feedback_applied") != "true":
        raise ValueError("continuum feedback was not applied")
    conservation = float(continuum["max_conservation_rel"])
    if not math.isfinite(conservation) or conservation > 1.0e-12:
        raise ValueError("distributed feedback conservation failed")
    if float(continuum["max_delta_U"]) <= 0.0 or float(continuum["max_delta_T"]) <= 0.0:
        raise ValueError("distributed continuum feedback is empty")
    if int(dsmc["inactive_parcels"]) != 0:
        raise ValueError("inactive DSMC parcels remain")
    if int(dsmc["ownership_balance_error"]) != 0:
        raise ValueError("distributed particle ledger failed")
    if float(dsmc["max_overlap_z"]) > 1.0:
        raise ValueError("distributed activation audit failed")
    if float(dsmc["max_flux_checksum"]) <= 0.0:
        raise ValueError("distributed physical feedback is empty")
    if dsmc.get("checkpoint_written") != "true":
        raise ValueError("distributed coupling state was not written")

    if (
        distributed_continuum.get("spatial_ranks") != "2"
        or distributed_continuum.get("unique_interface_ownership") != "true"
        or distributed_continuum.get("full_rhoCentralFoam_time_advance") != "true"
        or distributed_continuum.get("two_way_feedback_applied") != "true"
    ):
        raise ValueError("continuum distributed ownership marker is invalid")
    if (
        distributed_dsmc.get("spatial_ranks") != "2"
        or distributed_dsmc.get("global_interface_ownership") != "true"
        or distributed_dsmc.get("global_wall_flux_reduction") != "true"
        or distributed_dsmc.get("full_dsmcFoam_time_advance") != "true"
        or int(distributed_dsmc["global_final_parcels"]) <= 0
    ):
        raise ValueError("DSMC distributed ownership marker is invalid")

    return {
        "gate": "3J-LIVE-SPATIAL-DISTRIBUTION",
        "status": "PASS",
        "prerequisite": "Gate3I spatial-decomposition preflight PASS",
        "transport": "MUI-MPMD across two OpenFOAM sub-worlds",
        "decomposition_method": "simple Cartesian x-slabs",
        "continuum_spatial_ranks": 2,
        "dsmc_spatial_ranks": 2,
        "total_mpi_ranks": 4,
        "full_field_decomposition_completed": True,
        "live_distributed_openfoam_dsmc_completed": True,
        "full_rhoCentralFoam_time_advance": True,
        "full_dsmcFoam_time_advance": True,
        "physical_two_way_feedback_applied": True,
        "coupled_steps": 200,
        "coupling_windows": 1,
        "unique_continuum_interface_ownership": True,
        "unique_dsmc_cell_ownership": True,
        "global_dsmc_wall_flux_reduction": True,
        "maximum_feedback_conservation_relative_error": conservation,
        "maximum_particle_ownership_balance_error": 0,
        "maximum_inactive_parcels": 0,
        "global_final_parcels": int(distributed_dsmc["global_final_parcels"]),
        "distributed_checkpoint_restart_completed": False,
        "distributed_scaling_completed": False,
        "scope": "one live 2+2-rank spatially decomposed physical coupling window",
        "run_dir": run_dir,
        "live_log": str(live_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", required=True, type=Path)
    parser.add_argument("--decomposition", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    summary = analyze(args.live, args.decomposition, args.run_dir)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("GATE3J_LIVE_SPATIAL_DISTRIBUTION_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
