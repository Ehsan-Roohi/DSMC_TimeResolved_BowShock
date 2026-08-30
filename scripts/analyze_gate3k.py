#!/usr/bin/env python3
"""Analyze distributed OpenFOAM/MUI/DSMC checkpoint-restart equivalence."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path

def kv(line: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            out[key] = value
    return out

def markers(text: str, prefix: str, role: str) -> list[dict[str, str]]:
    return [kv(line.strip()) for line in text.splitlines()
            if line.strip().startswith(prefix) and f"role={role}" in line]

def one(text: str, prefix: str, role: str) -> dict[str, str]:
    found = markers(text, prefix, role)
    if len(found) != 1:
        raise ValueError(f"expected one {prefix.strip()} marker for {role}")
    return found[0]

def windows(text: str, role: str) -> list[dict[str, str]]:
    return markers(text, "GATE3G_WINDOW ", role)

def integer(item: dict[str, str], key: str) -> int:
    return int(item[key])

def number(item: dict[str, str], key: str) -> float:
    value = float(item[key])
    if not math.isfinite(value):
        raise ValueError(f"nonfinite {key}")
    return value

def relative(left: float, right: float) -> float:
    return abs(left-right)/max(abs(left), abs(right), 1.0e-300)

def validate(text: str, segment: str, start: int, stop: int, session: str):
    if "GATE3G_FAIL" in text or "GATE3J_FAIL" in text or "PIPELINE_FAIL" in text:
        raise ValueError(f"failure marker in {segment}")
    if f"mpi://continuum/{session}" not in text or f"mpi://dsmc/{session}" not in text:
        raise ValueError(f"incomplete MUI session in {segment}")
    continuum = one(text, "GATE3G_PASS ", "continuum_live")
    dsmc = one(text, "GATE3G_PASS ", "dsmc_live")
    dc = one(text, "GATE3J_PASS ", "continuum_distributed")
    dd = one(text, "GATE3J_PASS ", "dsmc_distributed")
    expected_windows = (stop-start)//200
    for item in (continuum, dsmc):
        if (item.get("segment") != segment or integer(item, "start_step") != start
                or integer(item, "stop_step") != stop
                or integer(item, "steps") != stop-start
                or integer(item, "first_step") != start+1
                or integer(item, "last_step") != stop
                or integer(item, "windows") != expected_windows):
            raise ValueError(f"step inventory failed in {segment}")
    if dc.get("spatial_ranks") != "2" or dd.get("spatial_ranks") != "2":
        raise ValueError(f"distributed rank inventory failed in {segment}")
    if dc.get("unique_interface_ownership") != "true":
        raise ValueError(f"continuum ownership failed in {segment}")
    if dd.get("global_interface_ownership") != "true":
        raise ValueError(f"DSMC ownership failed in {segment}")
    if dd.get("global_wall_flux_reduction") != "true":
        raise ValueError(f"wall-flux reduction failed in {segment}")
    if number(continuum, "max_conservation_rel") > 1.0e-12:
        raise ValueError(f"feedback conservation failed in {segment}")
    if integer(dsmc, "inactive_parcels") != 0:
        raise ValueError(f"inactive parcels in {segment}")
    if integer(dsmc, "ownership_balance_error") != 0:
        raise ValueError(f"particle ledger failed in {segment}")
    if number(dsmc, "max_overlap_z") > 1.0:
        raise ValueError(f"activation audit failed in {segment}")
    if number(dsmc, "max_flux_checksum") <= 0.0:
        raise ValueError(f"empty feedback in {segment}")
    if dsmc.get("checkpoint_written") != "true":
        raise ValueError(f"checkpoint missing in {segment}")
    if len(windows(text, "continuum")) != expected_windows:
        raise ValueError(f"continuum windows failed in {segment}")
    if len(windows(text, "dsmc")) != expected_windows:
        raise ValueError(f"DSMC windows failed in {segment}")
    return continuum, dsmc, dd

def analyze(continuous_path: Path, fresh_path: Path, restart_path: Path,
            checkpoint_path: Path, run_dir: str) -> dict[str, object]:
    continuous_text = continuous_path.read_text(encoding="utf-8", errors="replace")
    fresh_text = fresh_path.read_text(encoding="utf-8", errors="replace")
    restart_text = restart_path.read_text(encoding="utf-8", errors="replace")
    cc, cd, cdd = validate(continuous_text, "continuous", 0, 400, "gate3k_continuous")
    fc, fd, fdd = validate(fresh_text, "fresh", 0, 200, "gate3k_split")
    rc, rd, rdd = validate(restart_text, "restart", 200, 400, "gate3k_split")
    if "GATE3G_STATE_LOADED step=200 layers=64 accumulators=64" not in restart_text:
        raise ValueError("distributed coupling state was not restored")
    if integer(fc, "last_step")+1 != integer(rc, "first_step"):
        raise ValueError("restart has a duplicated or missing coupling step")
    if integer(cc, "adaptive_layer_changes") != (
        integer(fc, "adaptive_layer_changes")+integer(rc, "adaptive_layer_changes")
    ):
        raise ValueError("continuum adaptive inventory changed across restart")
    if integer(cd, "active_layer_changes") != (
        integer(fd, "active_layer_changes")+integer(rd, "active_layer_changes")
    ):
        raise ValueError("DSMC adaptive inventory changed across restart")

    continuous_flux = {integer(x, "window"): number(x, "flux_checksum")
                       for x in windows(continuous_text, "dsmc")}
    split_flux = {integer(x, "window"): number(x, "flux_checksum")
                  for x in windows(fresh_text, "dsmc")+windows(restart_text, "dsmc")}
    if set(continuous_flux) != {0, 1} or set(split_flux) != {0, 1}:
        raise ValueError("feedback window numbering is incomplete")
    post_restart_flux_difference = relative(continuous_flux[1], split_flux[1])
    if post_restart_flux_difference > 0.75:
        raise ValueError("post-restart flux exceeds stochastic tolerance")
    parcel_difference = relative(integer(cdd, "global_final_parcels"),
                                 integer(rdd, "global_final_parcels"))
    if parcel_difference > 0.25:
        raise ValueError("final parcel population exceeds stochastic tolerance")

    checkpoint = checkpoint_path.read_bytes()
    if not checkpoint.startswith(b"GATE3G_STATE_V1 200 64\n"):
        raise ValueError("checkpoint header is invalid")
    return {
        "gate": "3K-DISTRIBUTED-CHECKPOINT-RESTART",
        "status": "PASS",
        "prerequisite": "Gate3J live spatial distribution PASS",
        "transport": "MUI-MPMD across two OpenFOAM sub-worlds",
        "continuum_spatial_ranks": 2,
        "dsmc_spatial_ranks": 2,
        "total_mpi_ranks": 4,
        "continuous_steps": 400,
        "fresh_checkpoint_steps": 200,
        "restart_steps": 200,
        "restart_step_boundary": 200,
        "restart_first_resumed_step": 201,
        "restart_last_step": 400,
        "restart_has_no_duplicated_or_missing_step": True,
        "decomposed_openfoam_fields_and_cloud_restarted": True,
        "dynamic_layer_and_reservoir_state_restored": True,
        "checkpoint_sha256": hashlib.sha256(checkpoint).hexdigest(),
        "unique_interface_ownership_after_restart": True,
        "global_wall_flux_reduction_after_restart": True,
        "maximum_particle_ownership_balance_error": 0,
        "maximum_inactive_parcels": 0,
        "restart_matches_continuous_within_sampling_tolerance": True,
        "restart_matches_continuous_byte_for_byte": False,
        "restart_equivalence_scope": "distributed stochastic DSMC observables and exact coupling metadata",
        "post_restart_flux_relative_difference": post_restart_flux_difference,
        "final_parcel_population_relative_difference": parcel_difference,
        "maximum_feedback_conservation_relative_error": max(
            number(cc, "max_conservation_rel"), number(fc, "max_conservation_rel"),
            number(rc, "max_conservation_rel")),
        "distributed_scaling_completed": False,
        "run_dir": run_dir,
        "continuous_log": str(continuous_path),
        "fresh_log": str(fresh_path),
        "restart_log": str(restart_path),
    }

def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--continuous", required=True, type=Path)
    p.add_argument("--fresh", required=True, type=Path)
    p.add_argument("--restart", required=True, type=Path)
    p.add_argument("--checkpoint", required=True, type=Path)
    p.add_argument("--summary", required=True, type=Path)
    p.add_argument("--run-dir", required=True)
    a = p.parse_args()
    result = analyze(a.continuous, a.fresh, a.restart, a.checkpoint, a.run_dir)
    a.summary.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    print("GATE3K_DISTRIBUTED_RESTART_STATUS=PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
