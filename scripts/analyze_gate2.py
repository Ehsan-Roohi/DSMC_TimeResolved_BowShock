#!/usr/bin/env python3
"""Validate the Gate 2 interface/parcel audit and emit its JSON record."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path


FRAME_RE = re.compile(
    r"GATE2_FRAME frame=(?P<frame>\d+) active=(?P<active>\d+) "
    r"min_layers=(?P<min_layers>\d+) max_layers=(?P<max_layers>\d+) "
    r"activated=(?P<activated>\d+) deactivated=(?P<deactivated>\d+) "
    r"retained=(?P<retained>\d+) reused_parcels=(?P<reused>\d+) "
    r"created_parcels=(?P<created>\d+) inactive_parcels=(?P<inactive>\d+) "
    r"max_overlap_z=(?P<z>[-+0-9.eE]+)"
)
PASS_RE = re.compile(
    r"GATE2_PASS role=particle_manager frames=(?P<frames>\d+) "
    r"activation_threshold=(?P<activate>[-+0-9.eE]+) "
    r"deactivation_threshold=(?P<deactivate>[-+0-9.eE]+) "
    r"dynamic_activated=(?P<dynamic>\d+) deactivated=(?P<removed>\d+) "
    r"retained=(?P<retained>\d+) max_overlap_z=(?P<z>[-+0-9.eE]+) "
    r"external_reference_used=(?P<external>true|false)"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--indicator", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--run-dir", required=True)
    args = parser.parse_args()

    text = args.log.read_text(encoding="utf-8", errors="replace")
    frames = [
        {key: (float(value) if key == "z" else int(value))
         for key, value in match.groupdict().items()}
        for match in FRAME_RE.finditer(text)
    ]
    if [frame["frame"] for frame in frames] != list(range(9)):
        raise ValueError("Gate 2 frame markers are missing or out of order")
    if any(frame["inactive"] != 0 for frame in frames):
        raise ValueError("an inactive DSMC cell contains parcels")
    if any((frame["activated"] == 0) != (frame["created"] == 0) for frame in frames):
        raise ValueError("parcel creation is not confined to activated cells")
    if not any(frame["reused"] > 0 and frame["retained"] > 0 for frame in frames[1:]):
        raise ValueError("no retained particle identities were reused")

    final = PASS_RE.search(text)
    if final is None:
        raise ValueError("missing Gate 2 particle-manager PASS marker")
    pass_values = final.groupdict()
    activate = float(pass_values["activate"])
    deactivate = float(pass_values["deactivate"])
    maximum_z = float(pass_values["z"])
    if not activate > deactivate >= 0.0:
        raise ValueError("invalid hysteresis thresholds")
    if pass_values["external"] != "false":
        raise ValueError("automatic interface used an external reference")
    if int(pass_values["dynamic"]) <= 0 or int(pass_values["removed"]) <= 0:
        raise ValueError("forward/reverse replay did not exercise both transitions")
    if not math.isfinite(maximum_z) or maximum_z > 1.0:
        raise ValueError("overlap mismatch exceeds one sampling standard error")

    indicator_rows = list(csv.DictReader(args.indicator.open(encoding="utf-8")))
    if len(indicator_rows) != 9 * 800:
        raise ValueError("indicator CSV does not contain nine complete 800-cell frames")
    frame_counts: dict[int, int] = {}
    for row in indicator_rows:
        frame = int(row["frame"])
        frame_counts[frame] = frame_counts.get(frame, 0) + 1
        values = [float(row[name]) for name in ("indicator", "n", "ux", "uy", "uz", "T")]
        if not all(math.isfinite(value) for value in values):
            raise ValueError("indicator CSV contains non-finite state")
        if values[0] < 0.0 or values[1] <= 0.0 or values[-1] <= 0.0:
            raise ValueError("indicator CSV contains non-physical state")
    if frame_counts != {frame: 800 for frame in range(9)}:
        raise ValueError("indicator CSV frame inventory is incomplete")

    summary = {
        "gate": "2",
        "status": "PASS",
        "openfoam_version": "v2312",
        "case": "mach-4.65-rarefied-argon-flat-plate-transient-replay",
        "indicator": "max(Kn_density,Kn_temperature,Kn_velocity)",
        "activation_threshold": activate,
        "deactivation_threshold": deactivate,
        "hysteresis_gap": activate - deactivate,
        "frames": 9,
        "kinetic_cells": 800,
        "dynamic_activated_cells": int(pass_values["dynamic"]),
        "deactivated_cells": int(pass_values["removed"]),
        "retained_cell_events": int(pass_values["retained"]),
        "particle_identity_reuse": True,
        "creation_only_in_newly_activated_cells": True,
        "maximum_overlap_mismatch_sigma": maximum_z,
        "maximum_allowed_overlap_mismatch_sigma": 1.0,
        "external_reference_used": False,
        "full_dsmc_or_experiment_used_for_interface": False,
        "minimum_interface_height_m": min(frame["min_layers"] for frame in frames) * 0.0025,
        "maximum_interface_height_m": max(frame["max_layers"] for frame in frames) * 0.0025,
        "run_dir": args.run_dir,
        "indicator_csv": str(args.indicator),
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("GATE2_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
