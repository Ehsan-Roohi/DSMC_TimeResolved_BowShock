#!/usr/bin/env python3
"""Analyze the Gate 3D physical feedback, restart, adaptation, and scaling audit."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


PASS_RE = re.compile(
    r"GATE3D_PASS role=continuum mode=continuous .*?"
    r"activated_layers=(?P<activated>\d+) deactivated_layers=(?P<deactivated>\d+) .*?"
    r"max_raw_conservation_rel=(?P<raw>[-+0-9.eE]+) .*?"
    r"max_projected_conservation_rel=(?P<projected>[-+0-9.eE]+) .*?"
    r"max_relaxed_conservation_rel=(?P<relaxed>[-+0-9.eE]+)"
)
FEEDBACK_RE = re.compile(
    r"GATE3D_PASS role=continuum_feedback fields_written=true .*?"
    r"feedback_scale=(?P<scale>[-+0-9.eE]+) .*?"
    r"conservation_rel=(?P<conservation>[-+0-9.eE]+) .*?"
    r"max_delta_U=(?P<du>[-+0-9.eE]+) max_delta_T=(?P<dt>[-+0-9.eE]+)"
)
SCALING_RE = re.compile(
    r"GATE3D_SCALING ranks=(?P<ranks>\d+) iterations=(?P<iterations>\d+) "
    r"wall_seconds=(?P<time>[-+0-9.eE]+) mass=(?P<mass>[-+0-9.eE]+) "
    r"momentum_x=(?P<mx>[-+0-9.eE]+) momentum_y=(?P<my>[-+0-9.eE]+) "
    r"momentum_z=(?P<mz>[-+0-9.eE]+) energy=(?P<energy>[-+0-9.eE]+)"
)


def relative(actual: float, expected: float) -> float:
    return abs(actual - expected) / max(1.0, abs(actual), abs(expected))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--continuous-log", required=True, type=Path)
    parser.add_argument("--fresh-log", required=True, type=Path)
    parser.add_argument("--restart-log", required=True, type=Path)
    parser.add_argument("--feedback-log", required=True, type=Path)
    parser.add_argument("--scaling-log", required=True, action="append", type=Path)
    parser.add_argument("--continuous-state", required=True, type=Path)
    parser.add_argument("--resumed-state", required=True, type=Path)
    parser.add_argument("--continuous-csv", required=True, type=Path)
    parser.add_argument("--resumed-csv", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    continuous = args.continuous_log.read_text(encoding="utf-8", errors="replace")
    fresh = args.fresh_log.read_text(encoding="utf-8", errors="replace")
    restart = args.restart_log.read_text(encoding="utf-8", errors="replace")
    feedback = args.feedback_log.read_text(encoding="utf-8", errors="replace")
    if "GATE3D_FAIL" in continuous + fresh + restart + feedback:
        raise ValueError("a Gate 3D failure marker is present")
    for role in ("dsmc_replay", "continuum"):
        for mode, text in (("continuous", continuous), ("fresh", fresh), ("restart", restart)):
            if not re.search(rf"GATE3D_PASS role={role} mode={mode}\b", text):
                raise ValueError(f"missing {role}/{mode} PASS marker")

    match = PASS_RE.search(continuous)
    if not match:
        raise ValueError("continuous Gate 3D metrics are missing")
    activated = int(match.group("activated"))
    deactivated = int(match.group("deactivated"))
    raw = float(match.group("raw"))
    projected = float(match.group("projected"))
    relaxed = float(match.group("relaxed"))
    if activated + deactivated <= 0:
        raise ValueError("the physical adaptive interface did not move")
    if raw > 1.0e-10 or max(projected, relaxed) > 1.0e-12:
        raise ValueError("Gate 3D transport conservation failed")

    feedback_match = FEEDBACK_RE.search(feedback)
    if not feedback_match:
        raise ValueError("OpenFOAM feedback application PASS marker is missing")
    feedback_scale = float(feedback_match.group("scale"))
    feedback_conservation = float(feedback_match.group("conservation"))
    delta_u = float(feedback_match.group("du"))
    delta_t = float(feedback_match.group("dt"))
    if not 0.0 < feedback_scale <= 1.0 or feedback_conservation > 1.0e-12:
        raise ValueError("OpenFOAM feedback scaling or conservation failed")
    if delta_u <= 0.0 or delta_t <= 0.0:
        raise ValueError("OpenFOAM p/U/T fields were not changed")

    restart_identical = (
        args.continuous_state.read_bytes() == args.resumed_state.read_bytes()
        and args.continuous_csv.read_bytes() == args.resumed_csv.read_bytes()
    )
    if not restart_identical:
        raise ValueError("Gate 3D continuous and restarted feedback states differ")

    scaling: dict[int, dict[str, float | int]] = {}
    for path in args.scaling_log:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "GATE3D_SCALING_FAIL" in text:
            raise ValueError(f"scaling failure marker in {path}")
        scaling_match = SCALING_RE.search(text)
        if not scaling_match:
            raise ValueError(f"scaling record missing from {path}")
        ranks = int(scaling_match.group("ranks"))
        record = {
            "ranks": ranks,
            "iterations": int(scaling_match.group("iterations")),
            "wall_seconds": float(scaling_match.group("time")),
            "mass": float(scaling_match.group("mass")),
            "momentum_x": float(scaling_match.group("mx")),
            "momentum_y": float(scaling_match.group("my")),
            "momentum_z": float(scaling_match.group("mz")),
            "energy": float(scaling_match.group("energy")),
        }
        if record["wall_seconds"] <= 0.0:
            raise ValueError("nonpositive scaling time")
        scaling[ranks] = record
    if set(scaling) != {1, 2, 4}:
        raise ValueError("Gate 3D scaling ranks must be exactly 1, 2, and 4")
    baseline = scaling[1]
    maximum_scaling_difference = 0.0
    for ranks in (2, 4):
        for key in ("mass", "momentum_x", "momentum_y", "momentum_z", "energy"):
            maximum_scaling_difference = max(
                maximum_scaling_difference,
                relative(float(scaling[ranks][key]), float(baseline[key])),
            )
    if maximum_scaling_difference > 1.0e-12:
        raise ValueError("parallel coupling-kernel results depend on rank count")

    timing = []
    for ranks in (1, 2, 4):
        seconds = float(scaling[ranks]["wall_seconds"])
        timing.append(
            {
                "ranks": ranks,
                "wall_seconds": seconds,
                "speedup": float(baseline["wall_seconds"]) / seconds,
                "parallel_efficiency": float(baseline["wall_seconds"]) / (ranks * seconds),
            }
        )
    summary = {
        "gate": "3D-PHYSICAL-FEEDBACK-REPLAY",
        "status": "PASS",
        "physical_source": "Gate3C actual hybrid DSMC wall statistics",
        "transport": "MUI-MPMD reverse physical feedback",
        "continuum_target": "OpenFOAM-v2312 p/U/T snapshot",
        "feedback_faces": 64,
        "coupling_windows": 5,
        "two_way_flux_applied_to_continuum": True,
        "feedback_scale": feedback_scale,
        "feedback_conservation_relative_error": feedback_conservation,
        "maximum_velocity_change_m_per_s": delta_u,
        "maximum_temperature_change_K": delta_t,
        "adaptive_interface_completed": True,
        "activated_layer_events": activated,
        "deactivated_layer_events": deactivated,
        "maximum_raw_transport_conservation_relative_error": raw,
        "maximum_projected_conservation_relative_error": projected,
        "maximum_relaxed_conservation_relative_error": relaxed,
        "restart_matches_continuous_byte_for_byte": True,
        "parallel_scaling_completed": True,
        "parallel_scaling_scope": "physical-feedback coupling kernel",
        "scaling_rank_counts": [1, 2, 4],
        "scaling_numerical_invariance_relative_error": maximum_scaling_difference,
        "scaling": timing,
        "live_concurrent_openfoam_dsmc_completed": False,
        "run_dir": args.run_dir,
        "feedback_csv": str(args.continuous_csv),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("GATE3D_PHYSICAL_FEEDBACK_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
