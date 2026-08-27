from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/require_gate3d_pass.py"
ANALYZER = ROOT / "scripts/analyze_gate3e.py"


def valid_gate3d() -> dict[str, object]:
    return {
        "gate": "3D-PHYSICAL-FEEDBACK-REPLAY",
        "status": "PASS",
        "two_way_flux_applied_to_continuum": True,
        "adaptive_interface_completed": True,
        "restart_matches_continuous_byte_for_byte": True,
        "parallel_scaling_completed": True,
        "live_concurrent_openfoam_dsmc_completed": False,
        "scaling_rank_counts": [1, 2, 4],
        "feedback_conservation_relative_error": 1.0e-24,
        "maximum_raw_transport_conservation_relative_error": 0.0,
        "maximum_projected_conservation_relative_error": 0.0,
        "maximum_relaxed_conservation_relative_error": 1.0e-20,
        "scaling_numerical_invariance_relative_error": 1.0e-20,
    }


class Gate3EStaticTest(unittest.TestCase):
    def run_validator(self, data: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate3d.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_gate3d_prerequisite(self) -> None:
        accepted = self.run_validator(valid_gate3d())
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("GATE3D_PREREQUISITE=PASS", accepted.stdout)
        for key, value in (
            ("status", "FAIL"),
            ("restart_matches_continuous_byte_for_byte", False),
            ("live_concurrent_openfoam_dsmc_completed", True),
            ("maximum_relaxed_conservation_relative_error", 1.0e-6),
        ):
            record = valid_gate3d()
            record[key] = value
            self.assertNotEqual(self.run_validator(record).returncode, 0, key)

    def test_analyzer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            log = work / "live.log"
            windows = "".join(
                f"GATE3E_WINDOW role=continuum window={window} step={(window + 1) * 200} "
                "feedback_scale=0.1 conservation_rel=1e-20 max_delta_U=1 "
                "max_delta_T=2 adaptive_layer_changes=3\n"
                f"GATE3E_WINDOW role=dsmc window={window} step={(window + 1) * 200} "
                "samples=40 flux_checksum=1e-6 active_layer_changes=3\n"
                for window in range(5)
            )
            log.write_text(
                "MUI Rank 0 mpi://continuum/gate3e\n"
                "MUI Rank 1 mpi://dsmc/gate3e\n"
                + windows
                + "GATE3E_PASS role=continuum_live steps=1000 windows=5 "
                "full_rhoCentralFoam_time_advance=true "
                "two_way_feedback_applied=true adaptive_sampling_surface=true "
                "adaptive_layer_changes=3 min_feedback_scale=0.1 "
                "max_conservation_rel=1e-20 max_delta_U=1 max_delta_T=2\n"
                "GATE3E_PASS role=dsmc_live steps=1000 windows=5 "
                "final_parcels=100 inserted=20 active_layer_changes=3 "
                "max_flux_checksum=1e-6\n",
                encoding="utf-8",
            )
            summary = work / "summary.json"
            result = subprocess.run(
                [
                    sys.executable, str(ANALYZER),
                    "--log", str(log),
                    "--summary", str(summary),
                    "--run-dir", str(work),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(summary.read_text(encoding="utf-8"))
            self.assertTrue(record["live_concurrent_openfoam_dsmc_completed"])
            self.assertTrue(record["full_rhoCentralFoam_time_advance_completed"])
            self.assertFalse(record["adaptive_particle_domain_completed"])

    def test_live_mui_header_syntax(self) -> None:
        result = subprocess.run(
            [
                "g++", "-std=c++11", "-Wall", "-Wextra", "-Wpedantic", "-Werror",
                "-fsyntax-only", "-x", "c++", "-",
                "-I", str(ROOT / "tests/stubs"),
                "-I", str(ROOT / "openfoam/gate3c/common"),
                "-I", str(ROOT / "openfoam/gate3e/common"),
            ],
            input='#include "Gate3EMui.H"\nint main() { return gate3e::kineticSteps == 1000 ? 0 : 1; }\n',
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_solver_and_runner_scope(self) -> None:
        continuum = (
            ROOT / "openfoam/gate1b/rhoCentralFoamMUI/rhoCentralFoamMUI.C"
        ).read_text()
        dsmc = (
            ROOT / "openfoam/gate3c/dsmcFoamGate3C/dsmcFoamGate3C.C"
        ).read_text()
        runner = (ROOT / "scripts/run_gate3e.sh").read_text()
        self.assertIn("full_rhoCentralFoam_time_advance=true", continuum)
        self.assertIn("gate3e::fetchFeedback", continuum)
        self.assertIn("dsmc.evolve()", dsmc)
        self.assertIn("gate3e::pushFeedback", dsmc)
        self.assertIn("rhoCentralFoamGate3E", runner)
        self.assertIn("dsmcFoamGate3E", runner)
        self.assertNotIn("dsmc_replay", runner)


if __name__ == "__main__":
    unittest.main()
