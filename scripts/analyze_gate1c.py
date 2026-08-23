#!/usr/bin/env python3
"""Batch-mean uncertainty and wall-observable comparison for Gate 1C."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from pathlib import Path


WALL_RE = re.compile(
    r'GATE1C_WALL role="?(?P<role>\w+)"? step=(?P<step>\d+) '
    r"face=(?P<face>\d+) x=(?P<x>[-+0-9.eE]+) "
    r"q=(?P<q>[-+0-9.eE]+) tau=(?P<tau>[-+0-9.eE]+)"
)
T95_DF3 = 3.182446305
BATCHES = 4
EXPECTED_FACES = 40
EXPECTED_STEPS = list(range(600, 1601, 5))


def parse(path: Path, expected_role: str) -> dict[int, list[tuple[int, float, float, float]]]:
    observations: dict[int, list[tuple[int, float, float, float]]] = {}
    text = path.read_text(encoding="utf-8", errors="replace")
    pass_pattern = re.compile(
        rf'GATE1C_PASS role="?{re.escape(expected_role)}"?\b'
    )
    if not pass_pattern.search(text):
        raise ValueError(f"missing PASS marker for {expected_role} in {path}")
    for match in WALL_RE.finditer(text):
        if match.group("role") != expected_role:
            continue
        face = int(match.group("face"))
        observations.setdefault(face, []).append(
            (
                int(match.group("step")),
                float(match.group("x")),
                float(match.group("q")),
                float(match.group("tau")),
            )
        )
    if not observations:
        raise ValueError(f"no wall samples for {expected_role} in {path}")
    for samples in observations.values():
        samples.sort()
    return observations


def batch_statistics(values: list[float]) -> tuple[float, float, int]:
    block_size = len(values) // BATCHES
    if block_size < 2:
        raise ValueError("fewer than two samples per uncertainty block")
    used = values[: block_size * BATCHES]
    means = [
        statistics.fmean(used[i * block_size : (i + 1) * block_size])
        for i in range(BATCHES)
    ]
    mean = statistics.fmean(means)
    half_width = T95_DF3 * statistics.stdev(means) / math.sqrt(BATCHES)
    return mean, half_width, len(used)


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
    if set(reference) != set(hybrid):
        raise ValueError("reference and hybrid wall-face sets differ")
    expected_faces = set(range(EXPECTED_FACES))
    if set(reference) != expected_faces:
        raise ValueError(
            f"wall-face set is incomplete: expected {sorted(expected_faces)}, "
            f"got {sorted(reference)}"
        )

    rows: list[dict[str, float | int]] = []
    reference_q: list[float] = []
    reference_tau: list[float] = []
    hybrid_q: list[float] = []
    hybrid_tau: list[float] = []
    q_ci: list[float] = []
    tau_ci: list[float] = []
    used_samples = 0

    for face in sorted(reference):
        ref_samples = reference[face]
        hybrid_samples = hybrid[face]
        ref_steps = [sample[0] for sample in ref_samples]
        hybrid_steps = [sample[0] for sample in hybrid_samples]
        if ref_steps != hybrid_steps:
            raise ValueError(f"sampling steps differ on face {face}")
        if ref_steps != EXPECTED_STEPS:
            raise ValueError(
                f"sampling schedule is incomplete on face {face}: "
                f"expected {len(EXPECTED_STEPS)} samples, got {len(ref_steps)}"
            )
        expected_x = (face + 0.5)*0.0025
        if any(
            abs(sample[1] - expected_x) > 1.0e-12
            for sample in ref_samples + hybrid_samples
        ):
            raise ValueError(f"unexpected wall coordinate on face {face}")

        ref_q_mean, ref_q_ci, ref_used = batch_statistics(
            [sample[2] for sample in ref_samples]
        )
        ref_tau_mean, ref_tau_ci, _ = batch_statistics(
            [sample[3] for sample in ref_samples]
        )
        hybrid_q_mean, _, hybrid_used = batch_statistics(
            [sample[2] for sample in hybrid_samples]
        )
        hybrid_tau_mean, _, _ = batch_statistics(
            [sample[3] for sample in hybrid_samples]
        )
        if ref_used != hybrid_used:
            raise ValueError(f"used sample counts differ on face {face}")
        used_samples = ref_used

        reference_q.append(ref_q_mean)
        reference_tau.append(ref_tau_mean)
        hybrid_q.append(hybrid_q_mean)
        hybrid_tau.append(hybrid_tau_mean)
        q_ci.append(ref_q_ci)
        tau_ci.append(ref_tau_ci)
        rows.append(
            {
                "face": face,
                "x": ref_samples[0][1],
                "reference_q": ref_q_mean,
                "reference_q_ci95": ref_q_ci,
                "hybrid_q": hybrid_q_mean,
                "reference_tau": ref_tau_mean,
                "reference_tau_ci95": ref_tau_ci,
                "hybrid_tau": hybrid_tau_mean,
            }
        )

    tiny = 1.0e-300
    q_error = l2([a - b for a, b in zip(hybrid_q, reference_q)]) / max(
        l2(reference_q), tiny
    )
    tau_error = l2(
        [a - b for a, b in zip(hybrid_tau, reference_tau)]
    ) / max(l2(reference_tau), tiny)
    q_sampling = l2(q_ci) / max(l2(reference_q), tiny)
    tau_sampling = l2(tau_ci) / max(l2(reference_tau), tiny)
    q_threshold = max(0.03, q_sampling)
    tau_threshold = max(0.03, tau_sampling)
    q_pass = math.isfinite(q_error) and q_error <= q_threshold
    tau_pass = math.isfinite(tau_error) and tau_error <= tau_threshold
    status = "PASS" if q_pass and tau_pass else "FAIL"

    args.csv.parent.mkdir(parents=True, exist_ok=True)
    with args.csv.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "gate": "1C",
        "status": status,
        "openfoam_version": "v2312",
        "case": "mach-4.65-rarefied-argon-flat-plate",
        "coupling": "one-way-fixed-interface-continuum-to-dsmc",
        "interface_height_m": 0.015,
        "interface_selected_before_reference": True,
        "full_dsmc_executed_after_hybrid": True,
        "wall_faces": len(rows),
        "samples_per_face_observed": len(EXPECTED_STEPS),
        "samples_per_face_used": used_samples,
        "batch_count": BATCHES,
        "heat_flux_normalized_l2": q_error,
        "heat_flux_reference_ci95_normalized_l2": q_sampling,
        "heat_flux_acceptance_threshold": q_threshold,
        "heat_flux_pass": q_pass,
        "shear_normalized_l2": tau_error,
        "shear_reference_ci95_normalized_l2": tau_sampling,
        "shear_acceptance_threshold": tau_threshold,
        "shear_pass": tau_pass,
        "run_dir": args.run_dir,
        "wall_comparison_csv": str(args.csv),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"GATE1C_STATUS={status}")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
