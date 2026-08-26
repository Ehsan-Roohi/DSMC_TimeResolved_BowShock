#!/usr/bin/env python3
"""Compare Gate 3C cylinder wall observables with full-DSMC uncertainty."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from pathlib import Path


WALL_RE = re.compile(
    r'GATE3C_WALL role="?(?P<role>\w+)"? step=(?P<step>\d+) '
    r"face=(?P<face>\d+) theta=(?P<theta>[-+0-9.eE]+) "
    r"area=(?P<area>[-+0-9.eE]+) q=(?P<q>[-+0-9.eE]+) "
    r"drag=(?P<drag>[-+0-9.eE]+) lift=(?P<lift>[-+0-9.eE]+)"
)
T95_DF3 = 3.182446305
BATCHES = 4
EXPECTED_FACES = 64
EXPECTED_STEPS = list(range(600, 1601, 5))


def parse(path: Path, expected_role: str) -> dict[int, list[tuple[int, float, float, float, float, float]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not re.search(rf'GATE3C_PASS role="?{re.escape(expected_role)}"?\b', text):
        raise ValueError(f"missing PASS marker for {expected_role} in {path}")
    observations: dict[int, list[tuple[int, float, float, float, float, float]]] = {}
    for match in WALL_RE.finditer(text):
        if match.group("role") != expected_role:
            continue
        face = int(match.group("face"))
        observations.setdefault(face, []).append(
            (
                int(match.group("step")),
                float(match.group("theta")),
                float(match.group("area")),
                float(match.group("q")),
                float(match.group("drag")),
                float(match.group("lift")),
            )
        )
    for samples in observations.values():
        samples.sort()
    return observations


def batch_statistics(values: list[float]) -> tuple[float, float, int]:
    block_size = len(values) // BATCHES
    if block_size < 2:
        raise ValueError("fewer than two samples per uncertainty block")
    used = values[: block_size * BATCHES]
    means = [
        statistics.fmean(used[index * block_size : (index + 1) * block_size])
        for index in range(BATCHES)
    ]
    return (
        statistics.fmean(means),
        T95_DF3 * statistics.stdev(means) / math.sqrt(BATCHES),
        len(used),
    )


def l2(values: list[float]) -> float:
    return math.sqrt(sum(value * value for value in values))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--hybrid", required=True, type=Path)
    parser.add_argument("--summary", required=True, type=Path)
    parser.add_argument("--csv", required=True, type=Path)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    reference = parse(args.reference, "reference")
    hybrid = parse(args.hybrid, "hybrid")
    expected_faces = set(range(EXPECTED_FACES))
    if set(reference) != expected_faces or set(hybrid) != expected_faces:
        raise ValueError("reference or hybrid cylinder face inventory is incomplete")

    rows: list[dict[str, float | int]] = []
    reference_q: list[float] = []
    reference_drag: list[float] = []
    hybrid_q: list[float] = []
    hybrid_drag: list[float] = []
    q_ci: list[float] = []
    drag_ci: list[float] = []
    areas: list[float] = []
    used_samples = 0

    for face in range(EXPECTED_FACES):
        ref_samples = reference[face]
        hybrid_samples = hybrid[face]
        if [sample[0] for sample in ref_samples] != EXPECTED_STEPS:
            raise ValueError(f"reference sampling schedule is incomplete on face {face}")
        if [sample[0] for sample in hybrid_samples] != EXPECTED_STEPS:
            raise ValueError(f"hybrid sampling schedule is incomplete on face {face}")
        if any(abs(a[1] - b[1]) > 1.0e-12 for a, b in zip(ref_samples, hybrid_samples)):
            raise ValueError(f"reference and hybrid face angles differ on face {face}")
        if any(abs(a[2] - b[2]) > 1.0e-14 for a, b in zip(ref_samples, hybrid_samples)):
            raise ValueError(f"reference and hybrid face areas differ on face {face}")

        ref_q_mean, ref_q_ci, ref_used = batch_statistics([sample[3] for sample in ref_samples])
        ref_drag_mean, ref_drag_ci, _ = batch_statistics([sample[4] for sample in ref_samples])
        hybrid_q_mean, _, hybrid_used = batch_statistics([sample[3] for sample in hybrid_samples])
        hybrid_drag_mean, _, _ = batch_statistics([sample[4] for sample in hybrid_samples])
        if ref_used != hybrid_used:
            raise ValueError(f"used sample counts differ on face {face}")
        used_samples = ref_used
        area = ref_samples[0][2]
        areas.append(area)
        reference_q.append(ref_q_mean)
        reference_drag.append(ref_drag_mean)
        hybrid_q.append(hybrid_q_mean)
        hybrid_drag.append(hybrid_drag_mean)
        q_ci.append(ref_q_ci)
        drag_ci.append(ref_drag_ci)
        rows.append(
            {
                "face": face,
                "theta": ref_samples[0][1],
                "area": area,
                "reference_q": ref_q_mean,
                "reference_q_ci95": ref_q_ci,
                "hybrid_q": hybrid_q_mean,
                "reference_drag_density": ref_drag_mean,
                "reference_drag_ci95": ref_drag_ci,
                "hybrid_drag_density": hybrid_drag_mean,
            }
        )

    tiny = 1.0e-300
    q_error = l2([a - b for a, b in zip(hybrid_q, reference_q)]) / max(l2(reference_q), tiny)
    drag_error = l2([a - b for a, b in zip(hybrid_drag, reference_drag)]) / max(l2(reference_drag), tiny)
    q_sampling = l2(q_ci) / max(l2(reference_q), tiny)
    drag_sampling = l2(drag_ci) / max(l2(reference_drag), tiny)
    q_threshold = max(0.05, q_sampling)
    drag_threshold = max(0.05, drag_sampling)
    q_pass = math.isfinite(q_error) and q_error <= q_threshold
    drag_pass = math.isfinite(drag_error) and drag_error <= drag_threshold

    reference_total_drag = sum(value * area for value, area in zip(reference_drag, areas))
    hybrid_total_drag = sum(value * area for value, area in zip(hybrid_drag, areas))
    total_drag_relative_error = abs(hybrid_total_drag - reference_total_drag) / max(
        abs(reference_total_drag), tiny
    )
    status = "PASS" if q_pass and drag_pass else "FAIL"

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "gate": "3C-PHYSICAL-PREFLIGHT",
        "status": status,
        "openfoam_version": "v2312",
        "case": "mach-4.65-rarefied-argon-cylinder",
        "geometry": "body-fitted-annular-cylinder",
        "coupling": "one-way-fixed-radius-continuum-to-dsmc-via-MUI",
        "interface_radius_m": 0.025,
        "interface_selected_before_reference": True,
        "full_dsmc_executed_after_hybrid": True,
        "wall_faces": EXPECTED_FACES,
        "samples_per_face_observed": len(EXPECTED_STEPS),
        "samples_per_face_used": used_samples,
        "batch_count": BATCHES,
        "heat_flux_normalized_l2": q_error,
        "heat_flux_reference_ci95_normalized_l2": q_sampling,
        "heat_flux_acceptance_threshold": q_threshold,
        "heat_flux_pass": q_pass,
        "drag_density_normalized_l2": drag_error,
        "drag_reference_ci95_normalized_l2": drag_sampling,
        "drag_acceptance_threshold": drag_threshold,
        "drag_pass": drag_pass,
        "reference_total_drag_N": reference_total_drag,
        "hybrid_total_drag_N": hybrid_total_drag,
        "total_drag_relative_error": total_drag_relative_error,
        "two_way_flux_applied_to_continuum": False,
        "adaptive_interface_completed": False,
        "parallel_scaling_completed": False,
        "run_dir": args.run_dir,
        "wall_comparison_csv": str(args.csv),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"GATE3C_PHYSICAL_PREFLIGHT_STATUS={status}")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
