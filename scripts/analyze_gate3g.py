#!/usr/bin/env python3
"""Analyze Gate 3G live coupled restart and MPI scaling evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Iterable


SCALING_RE = re.compile(
    r"GATE3G_SCALING ranks=(?P<ranks>\d+) "
    r"iterations=(?P<iterations>\d+) "
    r"wall_seconds=(?P<wall>[-+0-9.eE]+) "
    r"checksum=(?P<checksum>\d+) "
    r"ownership_balance_error=(?P<balance>\d+)"
)


def key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def pass_marker(text: str, role: str) -> dict[str, str]:
    matches = [
        key_values(line.strip())
        for line in text.splitlines()
        if line.strip().startswith("GATE3G_PASS ")
        and f"role={role}" in line
    ]
    if len(matches) != 1:
        raise ValueError(f"expected one Gate 3G PASS marker for {role}")
    return matches[0]


def windows(text: str, role: str) -> list[dict[str, str]]:
    return [
        key_values(line.strip())
        for line in text.splitlines()
        if line.strip().startswith("GATE3G_WINDOW ")
        and f"role={role}" in line
    ]


def require_int(values: dict[str, str], key: str) -> int:
    return int(values[key])


def require_float(values: dict[str, str], key: str) -> float:
    value = float(values[key])
    if not math.isfinite(value):
        raise ValueError(f"nonfinite marker value: {key}")
    return value


def relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-300)


def validate_segment(
    text: str,
    name: str,
    start: int,
    stop: int,
    expected_windows: int,
) -> tuple[dict[str, str], dict[str, str]]:
    if "GATE3G_FAIL" in text or "GATE3F_FAIL" in text:
        raise ValueError(f"failure marker present in {name} segment")
    continuum = pass_marker(text, "continuum_live")
    dsmc = pass_marker(text, "dsmc_live")
    for marker in (continuum, dsmc):
        if marker.get("segment") != name:
            raise ValueError(f"incorrect segment name in {name}")
        if require_int(marker, "start_step") != start:
            raise ValueError(f"incorrect start step in {name}")
        if require_int(marker, "stop_step") != stop:
            raise ValueError(f"incorrect stop step in {name}")
        if require_int(marker, "steps") != stop - start:
            raise ValueError(f"incorrect step count in {name}")
        if require_int(marker, "first_step") != start + 1:
            raise ValueError(f"incorrect first step in {name}")
        if require_int(marker, "last_step") != stop:
            raise ValueError(f"incorrect last step in {name}")
        if require_int(marker, "windows") != expected_windows:
            raise ValueError(f"incorrect window count in {name}")
    if require_float(continuum, "max_conservation_rel") > 1.0e-12:
        raise ValueError(f"feedback conservation failed in {name}")
    if not 0.0 < require_float(continuum, "min_feedback_scale") <= 1.0:
        raise ValueError(f"invalid feedback scale in {name}")
    if require_float(continuum, "max_delta_U") <= 0.0:
        raise ValueError(f"no velocity feedback in {name}")
    if require_float(continuum, "max_delta_T") <= 0.0:
        raise ValueError(f"no temperature feedback in {name}")
    if require_int(dsmc, "inactive_parcels") != 0:
        raise ValueError(f"inactive particles remain in {name}")
    if require_int(dsmc, "ownership_balance_error") != 0:
        raise ValueError(f"particle ledger failed in {name}")
    if require_float(dsmc, "max_overlap_z") > 1.0:
        raise ValueError(f"activation mismatch failed in {name}")
    if require_float(dsmc, "max_flux_checksum") <= 0.0:
        raise ValueError(f"empty physical feedback in {name}")
    if dsmc.get("checkpoint_written") != "true":
        raise ValueError(f"checkpoint was not written in {name}")
    if len(windows(text, "continuum")) != expected_windows:
        raise ValueError(f"continuum window inventory failed in {name}")
    if len(windows(text, "dsmc")) != expected_windows:
        raise ValueError(f"DSMC window inventory failed in {name}")
    return continuum, dsmc


def analyze(
    continuous_path: Path,
    fresh_path: Path,
    restart_path: Path,
    checkpoint_path: Path,
    scaling_paths: Iterable[Path],
    run_dir: str,
) -> dict[str, object]:
    continuous_text = continuous_path.read_text(encoding="utf-8", errors="replace")
    fresh_text = fresh_path.read_text(encoding="utf-8", errors="replace")
    restart_text = restart_path.read_text(encoding="utf-8", errors="replace")
    required_sessions = (
        (continuous_text, "gate3g_continuous"),
        (fresh_text, "gate3g_split"),
        (restart_text, "gate3g_split"),
    )
    for text, session in required_sessions:
        if (
            f"mpi://continuum/{session}" not in text
            or f"mpi://dsmc/{session}" not in text
        ):
            raise ValueError(f"Gate 3G MUI session is incomplete: {session}")
    continuous_c, continuous_d = validate_segment(
        continuous_text, "continuous", 0, 1000, 5
    )
    fresh_c, fresh_d = validate_segment(fresh_text, "fresh", 0, 600, 3)
    restart_c, restart_d = validate_segment(
        restart_text, "restart", 600, 1000, 2
    )
    if "GATE3G_STATE_LOADED step=600 layers=64 accumulators=64" not in restart_text:
        raise ValueError("restart did not restore the Gate 3G coupling state")
    if require_int(fresh_c, "last_step") + 1 != require_int(restart_c, "first_step"):
        raise ValueError("coupled restart contains a duplicated or missing step")

    for key in ("adaptive_layer_changes",):
        if require_int(continuous_c, key) != (
            require_int(fresh_c, key) + require_int(restart_c, key)
        ):
            raise ValueError("continuum adaptive inventory changed across restart")
    if require_int(continuous_d, "active_layer_changes") != (
        require_int(fresh_d, "active_layer_changes")
        + require_int(restart_d, "active_layer_changes")
    ):
        raise ValueError("DSMC adaptive inventory changed across restart")

    continuous_flux = {
        require_int(item, "window"): require_float(item, "flux_checksum")
        for item in windows(continuous_text, "dsmc")
    }
    split_flux = {
        require_int(item, "window"): require_float(item, "flux_checksum")
        for item in windows(fresh_text, "dsmc") + windows(restart_text, "dsmc")
    }
    if set(continuous_flux) != set(range(5)) or set(split_flux) != set(range(5)):
        raise ValueError("global feedback window numbering is incomplete")
    flux_differences = [
        relative_difference(continuous_flux[index], split_flux[index])
        for index in range(5)
    ]
    maximum_post_restart_flux_difference = max(flux_differences[3:])
    if maximum_post_restart_flux_difference > 0.75:
        raise ValueError("post-restart DSMC flux exceeds sampling tolerance")
    parcel_difference = relative_difference(
        require_int(continuous_d, "final_parcels"),
        require_int(restart_d, "final_parcels"),
    )
    if parcel_difference > 0.25:
        raise ValueError("post-restart parcel population is not statistically consistent")

    checkpoint = checkpoint_path.read_bytes()
    if not checkpoint.startswith(b"GATE3G_STATE_V1 600 64\n"):
        raise ValueError("Gate 3G checkpoint header is invalid")
    checkpoint_sha256 = hashlib.sha256(checkpoint).hexdigest()

    scaling: list[dict[str, object]] = []
    checksum: int | None = None
    baseline_wall = 0.0
    for path in scaling_paths:
        match = SCALING_RE.search(path.read_text(encoding="utf-8", errors="replace"))
        if match is None:
            raise ValueError(f"invalid Gate 3G scaling log: {path}")
        ranks = int(match.group("ranks"))
        wall = float(match.group("wall"))
        current_checksum = int(match.group("checksum"))
        balance = int(match.group("balance"))
        if wall <= 0.0 or balance != 0:
            raise ValueError("Gate 3G scaling kernel failed")
        if checksum is None:
            checksum = current_checksum
            baseline_wall = wall
        elif current_checksum != checksum:
            raise ValueError("Gate 3G scaling checksum is rank-dependent")
        scaling.append(
            {
                "ranks": ranks,
                "wall_seconds": wall,
                "speedup": baseline_wall / wall,
                "parallel_efficiency": baseline_wall / (wall * ranks),
            }
        )
    if [item["ranks"] for item in scaling] != [1, 2, 4]:
        raise ValueError("Gate 3G scaling ranks must be exactly 1, 2, and 4")

    return {
        "gate": "3G-LIVE-COUPLED-RESTART",
        "status": "PASS",
        "prerequisite": "Gate3F dynamic particle-domain PASS",
        "transport": "MUI-MPMD synchronous bidirectional exchange",
        "continuum_solver": "derived OpenFOAM-v2312 rhoCentralFoam",
        "kinetic_solver": "derived OpenFOAM-v2312 dsmcFoam",
        "continuous_live_run_completed": True,
        "fresh_checkpoint_segment_completed": True,
        "live_restart_segment_completed": True,
        "restart_step_boundary": 600,
        "restart_first_resumed_step": 601,
        "restart_last_step": 1000,
        "restart_has_no_duplicated_or_missing_coupling_step": True,
        "dynamic_layer_and_reservoir_state_restored": True,
        "checkpoint_sha256": checkpoint_sha256,
        "particle_ownership_exact_before_and_after_restart": True,
        "maximum_particle_ownership_balance_error": 0,
        "maximum_inactive_parcels": 0,
        "restart_matches_continuous_within_sampling_tolerance": True,
        "restart_matches_continuous_byte_for_byte": False,
        "restart_equivalence_scope": "stochastic DSMC observables and exact coupling metadata",
        "maximum_post_restart_flux_relative_difference": maximum_post_restart_flux_difference,
        "final_parcel_population_relative_difference": parcel_difference,
        "maximum_feedback_conservation_relative_error": max(
            require_float(continuous_c, "max_conservation_rel"),
            require_float(fresh_c, "max_conservation_rel"),
            require_float(restart_c, "max_conservation_rel"),
        ),
        "parallel_scaling_completed": True,
        "parallel_scaling_scope": "dynamic particle-ownership and checkpoint kernel",
        "scaling_rank_counts": [1, 2, 4],
        "scaling_checksum_rank_invariant": True,
        "scaling": scaling,
        "run_dir": run_dir,
        "continuous_log": str(continuous_path),
        "fresh_log": str(fresh_path),
        "restart_log": str(restart_path),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--continuous", required=True, type=Path)
    parser.add_argument("--fresh", required=True, type=Path)
    parser.add_argument("--restart", required=True, type=Path)
    parser.add_argument("--checkpoint", required=True, type=Path)
    parser.add_argument("--scaling", required=True, type=Path, nargs=3)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    summary = analyze(
        args.continuous,
        args.fresh,
        args.restart,
        args.checkpoint,
        args.scaling,
        args.run_dir,
    )
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("GATE3G_LIVE_RESTART_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
