#!/usr/bin/env python3
"""Analyze the live concurrent Gate 3E rhoCentralFoam/DSMC run."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


CONTINUUM_RE = re.compile(
    r"GATE3E_PASS role=continuum_live steps=(?P<steps>\d+) "
    r"windows=(?P<windows>\d+) full_rhoCentralFoam_time_advance=true "
    r"two_way_feedback_applied=true adaptive_sampling_surface=true "
    r"adaptive_layer_changes=(?P<changes>\d+) "
    r"min_feedback_scale=(?P<scale>[-+0-9.eE]+) "
    r"max_conservation_rel=(?P<conservation>[-+0-9.eE]+) "
    r"max_delta_U=(?P<du>[-+0-9.eE]+) "
    r"max_delta_T=(?P<dt>[-+0-9.eE]+)"
)
DSMC_RE = re.compile(
    r"GATE3E_PASS role=dsmc_live steps=(?P<steps>\d+) "
    r"windows=(?P<windows>\d+) final_parcels=(?P<parcels>\d+) "
    r"inserted=(?P<inserted>\d+) active_layer_changes=(?P<changes>\d+) "
    r"max_flux_checksum=(?P<checksum>[-+0-9.eE]+)"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    text = args.log.read_text(encoding="utf-8", errors="replace")
    if "GATE3E_FAIL" in text or "GATE3C_FAIL" in text:
        raise ValueError("a live-coupling failure marker is present")
    continuum = CONTINUUM_RE.search(text)
    dsmc = DSMC_RE.search(text)
    if not continuum or not dsmc:
        raise ValueError("Gate 3E final PASS markers are incomplete")
    continuum_values = {key: float(value) for key, value in continuum.groupdict().items()}
    dsmc_values = {key: float(value) for key, value in dsmc.groupdict().items()}
    if int(continuum_values["steps"]) != 1000 or int(dsmc_values["steps"]) != 1000:
        raise ValueError("Gate 3E must complete exactly 1000 synchronized steps")
    if int(continuum_values["windows"]) != 5 or int(dsmc_values["windows"]) != 5:
        raise ValueError("Gate 3E must complete exactly five feedback windows")
    if int(continuum_values["changes"]) <= 0 or int(dsmc_values["changes"]) <= 0:
        raise ValueError("adaptive sampling surface did not move")
    if not 0.0 < continuum_values["scale"] <= 1.0:
        raise ValueError("invalid live feedback scale")
    if continuum_values["conservation"] > 1.0e-12:
        raise ValueError("live feedback conservation failed")
    if continuum_values["du"] <= 0.0 or continuum_values["dt"] <= 0.0:
        raise ValueError("live feedback did not change continuum state")
    if dsmc_values["parcels"] <= 0 or dsmc_values["checksum"] <= 0.0:
        raise ValueError("live DSMC physical feedback is empty")
    if len(re.findall(r"GATE3E_WINDOW role=continuum\b", text)) != 5:
        raise ValueError("continuum window inventory is incomplete")
    if len(re.findall(r"GATE3E_WINDOW role=dsmc\b", text)) != 5:
        raise ValueError("DSMC window inventory is incomplete")
    if "mpi://continuum/gate3e" not in text or "mpi://dsmc/gate3e" not in text:
        raise ValueError("MUI live MPMD identifiers are missing")

    summary = {
        "gate": "3E-LIVE-CONCURRENT-COUPLING",
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
        "adaptive_particle_domain_completed": False,
        "synchronized_steps": 1000,
        "synchronized_relative_time_step_s": 1.0e-7,
        "coupling_window_duration_s": 2.0e-5,
        "coupling_windows": 5,
        "samples_per_window": 40,
        "continuum_adaptive_layer_changes": int(continuum_values["changes"]),
        "dsmc_observed_layer_changes": int(dsmc_values["changes"]),
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
    print("GATE3E_LIVE_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
