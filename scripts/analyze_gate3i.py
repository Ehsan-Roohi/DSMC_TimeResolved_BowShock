#!/usr/bin/env python3
"""Analyze OpenFOAM decomposition and multi-rank MUI preflight evidence."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable


DECOMP_RE = re.compile(
    r"GATE3I_DECOMPOSITION role=(continuum|dsmc) ranks=(\d+) "
    r"processor_dirs=(\d+) mesh_ok=true"
)
MUI_RE = re.compile(
    r"GATE3I_MUI_PASS role=(continuum|dsmc) local_rank=(\d+) "
    r"app_ranks=(\d+) world_ranks=(\d+) bidirectional=true"
)


def analyze(log_paths: Iterable[Path], run_dir: str) -> dict[str, object]:
    records: list[dict[str, int]] = []
    for path in log_paths:
        text = path.read_text(encoding="utf-8", errors="replace")
        if "GATE3I_FAIL" in text or "GATE3I_PIPELINE_FAIL" in text:
            raise ValueError(f"failure marker present in {path}")
        decompositions = DECOMP_RE.findall(text)
        probes = MUI_RE.findall(text)
        ranks = int(path.stem.rsplit("_", 1)[-1])
        if ranks not in (1, 2, 4):
            raise ValueError("unexpected Gate 3I rank count")
        expected_dirs = 0 if ranks == 1 else ranks
        if sorted(decompositions) != sorted(
            [("continuum", str(ranks), str(expected_dirs)),
             ("dsmc", str(ranks), str(expected_dirs))]
        ):
            raise ValueError(f"incomplete decomposition inventory in {path}")
        expected_probes = sorted(
            (role, str(local_rank), str(ranks), str(2*ranks))
            for role in ("continuum", "dsmc")
            for local_rank in range(ranks)
        )
        if sorted(probes) != expected_probes:
            raise ValueError(f"incomplete multi-rank MUI inventory in {path}")
        records.append(
            {"ranks_per_application": ranks, "total_mpi_ranks": 2*ranks}
        )
    if [item["ranks_per_application"] for item in records] != [1, 2, 4]:
        raise ValueError("Gate 3I logs must be ordered 1, 2, and 4")
    return {
        "gate": "3I-SPATIAL-DECOMPOSITION-PREFLIGHT",
        "status": "PASS",
        "prerequisite": "Gate3H full-solver ensemble scaling PASS",
        "openfoam_cases": ["continuum", "hybrid_dsmc"],
        "decomposition_method": "scotch",
        "decomposed_openfoam_meshes_validated": True,
        "parallel_checkMesh_completed": True,
        "multi_rank_bidirectional_mui_transport_completed": True,
        "ranks_per_application": [1, 2, 4],
        "total_mpi_rank_counts": [2, 4, 8],
        "rank_inventory": records,
        "live_distributed_openfoam_dsmc_completed": False,
        "scope": "decomposition and MUI transport preflight; no distributed solver advance",
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
    print("GATE3I_SPATIAL_DECOMPOSITION_PREFLIGHT_STATUS=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
