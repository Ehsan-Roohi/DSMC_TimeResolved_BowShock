#!/usr/bin/env python3
"""Require the verified Gate 3G live checkpoint/restart result."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3g_pass.py SUMMARY")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    required_true = (
        "continuous_live_run_completed",
        "fresh_checkpoint_segment_completed",
        "live_restart_segment_completed",
        "restart_has_no_duplicated_or_missing_coupling_step",
        "dynamic_layer_and_reservoir_state_restored",
        "particle_ownership_exact_before_and_after_restart",
        "restart_matches_continuous_within_sampling_tolerance",
        "parallel_scaling_completed",
        "scaling_checksum_rank_invariant",
    )
    valid = (
        data.get("gate") == "3G-LIVE-COUPLED-RESTART"
        and data.get("status") == "PASS"
        and all(data.get(key) is True for key in required_true)
        and data.get("restart_step_boundary") == 600
        and data.get("restart_first_resumed_step") == 601
        and data.get("restart_last_step") == 1000
        and data.get("restart_matches_continuous_byte_for_byte") is False
        and int(data.get("maximum_particle_ownership_balance_error", -1)) == 0
        and int(data.get("maximum_inactive_parcels", -1)) == 0
        and float(data.get("maximum_post_restart_flux_relative_difference", 1.0)) <= 0.75
        and float(data.get("final_parcel_population_relative_difference", 1.0)) <= 0.25
        and float(data.get("maximum_feedback_conservation_relative_error", 1.0)) <= 1.0e-12
        and data.get("scaling_rank_counts") == [1, 2, 4]
        and isinstance(data.get("run_dir"), str)
        and bool(data.get("run_dir"))
    )
    if not valid:
        raise SystemExit(f"Gate 3G prerequisite is not a verified PASS: {path}")
    print(f"GATE3G_PREREQUISITE=PASS artifact={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
