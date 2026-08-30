#!/usr/bin/env python3
"""Require the immutable verified Gate 3J distributed-live result."""
from __future__ import annotations
import json
import sys
from pathlib import Path

def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3j_pass.py SUMMARY")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    valid = (
        data.get("gate") == "3J-LIVE-SPATIAL-DISTRIBUTION"
        and data.get("status") == "PASS"
        and data.get("continuum_spatial_ranks") == 2
        and data.get("dsmc_spatial_ranks") == 2
        and data.get("total_mpi_ranks") == 4
        and data.get("live_distributed_openfoam_dsmc_completed") is True
        and data.get("full_rhoCentralFoam_time_advance") is True
        and data.get("full_dsmcFoam_time_advance") is True
        and data.get("physical_two_way_feedback_applied") is True
        and data.get("unique_continuum_interface_ownership") is True
        and data.get("unique_dsmc_cell_ownership") is True
        and data.get("global_dsmc_wall_flux_reduction") is True
        and data.get("maximum_particle_ownership_balance_error") == 0
        and data.get("maximum_inactive_parcels") == 0
        and data.get("distributed_checkpoint_restart_completed") is False
    )
    if not valid:
        raise SystemExit(f"Gate 3J prerequisite is not a verified PASS: {path}")
    print(f"GATE3J_PREREQUISITE=PASS artifact={path.resolve()}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
