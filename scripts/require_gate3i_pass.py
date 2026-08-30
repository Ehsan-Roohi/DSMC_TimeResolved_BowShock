#!/usr/bin/env python3
"""Require the verified Gate 3I spatial-decomposition preflight result."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: require_gate3i_pass.py SUMMARY")
    path = Path(sys.argv[1])
    data = json.loads(path.read_text(encoding="utf-8"))
    valid = (
        data.get("gate") == "3I-SPATIAL-DECOMPOSITION-PREFLIGHT"
        and data.get("status") == "PASS"
        and data.get("decomposed_openfoam_meshes_validated") is True
        and data.get("parallel_checkMesh_completed") is True
        and data.get("multi_rank_bidirectional_mui_transport_completed") is True
        and data.get("ranks_per_application") == [1, 2, 4]
        and data.get("total_mpi_rank_counts") == [2, 4, 8]
        and data.get("live_distributed_openfoam_dsmc_completed") is False
    )
    if not valid:
        raise SystemExit(f"Gate 3I prerequisite is not a verified PASS: {path}")
    print(f"GATE3I_PREREQUISITE=PASS artifact={path.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
