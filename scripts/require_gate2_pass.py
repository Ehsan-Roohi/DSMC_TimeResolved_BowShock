#!/usr/bin/env python3
import json
import math
import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate2_pass.py gate2_summary.json")
    path = pathlib.Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"Gate 2 PASS artifact is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    required_true = (
        "particle_identity_reuse",
        "creation_only_in_newly_activated_cells",
    )
    if str(data.get("gate")) != "2" or data.get("status") != "PASS":
        raise SystemExit("Gate 2 artifact does not report PASS")
    for key in required_true:
        if data.get(key) is not True:
            raise SystemExit(f"Gate 2 artifact failed required invariant: {key}")
    mismatch = float(data.get("maximum_overlap_mismatch_sigma", math.inf))
    allowed = float(data.get("maximum_allowed_overlap_mismatch_sigma", -math.inf))
    if not math.isfinite(mismatch) or not math.isfinite(allowed) or mismatch > allowed:
        raise SystemExit("Gate 2 overlap mismatch exceeds its acceptance limit")
    if int(data.get("dynamic_activated_cells", 0)) <= 0:
        raise SystemExit("Gate 2 artifact contains no dynamic activation")
    if int(data.get("deactivated_cells", 0)) <= 0:
        raise SystemExit("Gate 2 artifact contains no deactivation")
    print(f"GATE2_PREREQUISITE=PASS artifact={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
