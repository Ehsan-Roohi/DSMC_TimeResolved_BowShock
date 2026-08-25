#!/usr/bin/env python3
import json
import math
import pathlib
import sys


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3a_pass.py gate3a_summary.json")
    path = pathlib.Path(sys.argv[1])
    if not path.is_file():
        raise SystemExit(f"Gate 3A PASS artifact is missing: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if str(data.get("gate")) != "3A" or data.get("status") != "PASS":
        raise SystemExit("Gate 3A artifact does not report PASS")
    if data.get("transport") != "MUI-MPMD":
        raise SystemExit("Gate 3A artifact does not prove MUI MPMD transport")
    if data.get("restart_matches_continuous_byte_for_byte") is not True:
        raise SystemExit("Gate 3A restart determinism invariant failed")
    if data.get("unresolved_window_skipped") is not True:
        raise SystemExit("Gate 3A unresolved-window guard was not exercised")

    raw = float(data.get("maximum_raw_rbf_conservation_relative_error", math.inf))
    raw_limit = float(data.get("maximum_allowed_raw_rbf_conservation_relative_error", -math.inf))
    mapped = float(data.get("maximum_mapped_conservation_relative_error", math.inf))
    relaxed = float(data.get("maximum_relaxed_conservation_relative_error", math.inf))
    tolerance = float(data.get("conservation_tolerance", -math.inf))
    values = (raw, raw_limit, mapped, relaxed, tolerance)
    if not all(math.isfinite(value) for value in values):
        raise SystemExit("Gate 3A conservation metrics are non-finite")
    if raw < 0.0 or raw > raw_limit or raw_limit <= 0.0:
        raise SystemExit("Gate 3A raw RBF defect exceeds its acceptance limit")
    if tolerance <= 0.0 or mapped < 0.0 or relaxed < 0.0:
        raise SystemExit("Gate 3A conservation tolerance is invalid")
    if mapped > tolerance or relaxed > tolerance:
        raise SystemExit("Gate 3A projected or relaxed conservation failed")
    if int(data.get("windows", 0)) < 3:
        raise SystemExit("Gate 3A artifact contains too few flux windows")
    print(f"GATE3A_PREREQUISITE=PASS artifact={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
