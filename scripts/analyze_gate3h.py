#!/usr/bin/env python3
"""Analyze full-solver MPMD ensemble-throughput scaling evidence."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Iterable


SCALE_RE = re.compile(
    r"GATE3H_SCALING replicas=(?P<replicas>\d+) "
    r"solver_ranks=(?P<ranks>\d+) steps_per_replica=(?P<steps>\d+) "
    r"wall_seconds=(?P<wall>[-+0-9.eE]+)"
)


def key_values(line: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for token in line.split()[1:]:
        if "=" in token:
            key, value = token.split("=", 1)
            values[key] = value
    return values


def relative_difference(left: float, right: float) -> float:
    return abs(left - right) / max(abs(left), abs(right), 1.0e-300)


def analyze(log_paths: Iterable[Path], run_dir: str) -> dict[str, object]:
    records: list[dict[str, object]] = []
    fluxes: list[float] = []
    populations: list[int] = []
    baseline_wall = 0.0
    maximum_conservation = 0.0
    for path in log_paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "GATE3G_FAIL" in text or "GATE3H_PIPELINE_FAIL" in text:
            raise ValueError(f"failure marker present in {path}")
        match = SCALE_RE.search(text)
        if match is None:
            raise ValueError(f"missing Gate 3H scaling marker in {path}")
        replicas = int(match.group("replicas"))
        solver_ranks = int(match.group("ranks"))
        steps = int(match.group("steps"))
        wall = float(match.group("wall"))
        if replicas not in (1, 2, 4) or solver_ranks != 2 * replicas:
            raise ValueError("invalid Gate 3H rank inventory")
        if steps != 400 or not math.isfinite(wall) or wall <= 0.0:
            raise ValueError("invalid Gate 3H workload or timing")

        continuum = [
            key_values(line)
            for line in text.splitlines()
            if line.startswith("GATE3G_PASS role=continuum_live ")
        ]
        dsmc = [
            key_values(line)
            for line in text.splitlines()
            if line.startswith("GATE3G_PASS role=dsmc_live ")
        ]
        if len(continuum) != replicas or len(dsmc) != replicas:
            raise ValueError("incomplete full-solver replica inventory")
        expected_segments = {f"scale_{replicas}_{index}" for index in range(replicas)}
        if {item.get("segment") for item in continuum} != expected_segments:
            raise ValueError("continuum replica sessions are incomplete")
        if {item.get("segment") for item in dsmc} != expected_segments:
            raise ValueError("DSMC replica sessions are incomplete")

        for marker in continuum:
            if (
                int(marker["steps"]) != 400
                or int(marker["first_step"]) != 1
                or int(marker["last_step"]) != 400
                or int(marker["windows"]) != 2
                or marker.get("full_rhoCentralFoam_time_advance") != "true"
                or marker.get("two_way_feedback_applied") != "true"
            ):
                raise ValueError("invalid continuum full-solver marker")
            conservation = float(marker["max_conservation_rel"])
            if conservation > 1.0e-12 or float(marker["min_feedback_scale"]) <= 0.0:
                raise ValueError("continuum conservation or feedback failed")
            maximum_conservation = max(maximum_conservation, conservation)
        for marker in dsmc:
            if (
                int(marker["steps"]) != 400
                or int(marker["first_step"]) != 1
                or int(marker["last_step"]) != 400
                or int(marker["windows"]) != 2
                or int(marker["inactive_parcels"]) != 0
                or int(marker["ownership_balance_error"]) != 0
                or marker.get("checkpoint_written") != "true"
            ):
                raise ValueError("invalid DSMC full-solver marker")
            if float(marker["max_overlap_z"]) > 1.0:
                raise ValueError("DSMC overlap audit failed")
            flux = float(marker["max_flux_checksum"])
            population = int(marker["final_parcels"])
            if flux <= 0.0 or population <= 0:
                raise ValueError("empty DSMC physical result")
            fluxes.append(flux)
            populations.append(population)

        if baseline_wall == 0.0:
            baseline_wall = wall
        speedup = replicas * baseline_wall / wall
        records.append(
            {
                "coupled_replicas": replicas,
                "total_solver_ranks": solver_ranks,
                "wall_seconds": wall,
                "throughput_speedup": speedup,
                "parallel_efficiency": speedup / replicas,
            }
        )

    if [item["coupled_replicas"] for item in records] != [1, 2, 4]:
        raise ValueError("Gate 3H replica counts must be exactly 1, 2, and 4")
    baseline_flux = fluxes[0]
    baseline_population = populations[0]
    max_flux_difference = max(relative_difference(value, baseline_flux) for value in fluxes)
    max_population_difference = max(
        relative_difference(value, baseline_population) for value in populations
    )
    if max_flux_difference > 0.75 or max_population_difference > 0.25:
        raise ValueError("full-solver replicas exceed DSMC sampling tolerance")

    return {
        "gate": "3H-FULL-SOLVER-ENSEMBLE-SCALING",
        "status": "PASS",
        "prerequisite": "Gate3G live coupled checkpoint/restart PASS",
        "transport": "independent MUI-MPMD live coupled solver pairs",
        "continuum_solver": "derived OpenFOAM-v2312 rhoCentralFoam",
        "kinetic_solver": "derived OpenFOAM-v2312 dsmcFoam",
        "full_solver_parallel_scaling_completed": True,
        "parallel_scaling_scope": "concurrent independent live coupled full-solver replicas",
        "domain_decomposition_completed": False,
        "coupled_replica_counts": [1, 2, 4],
        "total_solver_rank_counts": [2, 4, 8],
        "steps_per_replica": 400,
        "coupling_windows_per_replica": 2,
        "all_replicas_advanced_both_full_solvers": True,
        "all_replicas_applied_two_way_feedback": True,
        "all_replicas_closed_particle_ownership_ledger": True,
        "maximum_feedback_conservation_relative_error": maximum_conservation,
        "maximum_flux_relative_difference": max_flux_difference,
        "maximum_final_parcel_population_relative_difference": max_population_difference,
        "scaling": records,
        "run_dir": run_dir,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logs", required=True, type=Path, nargs=3)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()
    summary = analyze(args.logs, args.run_dir)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("GATE3H_FULL_SOLVER_SCALING_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
