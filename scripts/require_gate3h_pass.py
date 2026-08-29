#!/usr/bin/env python3
"""Require the verified Gate 3H full-solver ensemble result."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3h_pass.py SUMMARY")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    valid = (
        data.get("gate") == "3H-FULL-SOLVER-ENSEMBLE-SCALING"
        and data.get("status") == "PASS"
        and data.get("full_solver_parallel_scaling_completed") is True
        and data.get("domain_decomposition_completed") is False
        and data.get("coupled_replica_counts") == [1, 2, 4]
        and data.get("total_solver_rank_counts") == [2, 4, 8]
        and data.get("all_replicas_advanced_both_full_solvers") is True
        and data.get("all_replicas_applied_two_way_feedback") is True
        and data.get("all_replicas_closed_particle_ownership_ledger") is True
        and float(data.get("maximum_feedback_conservation_relative_error", 1.0)) <= 1.0e-12
    )
    if not valid:
        raise SystemExit(f"Gate 3H prerequisite is not a verified PASS: {path}")
    print(f"GATE3H_PREREQUISITE=PASS artifact={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
