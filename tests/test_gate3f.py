from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/require_gate3e_pass.py"
ANALYZER = ROOT / "scripts/analyze_gate3f.py"


def valid_gate3e() -> dict[str, object]:
    return {
        "gate": "3E-LIVE-CONCURRENT-COUPLING",
        "status": "PASS",
        "live_concurrent_openfoam_dsmc_completed": True,
        "continuum_and_dsmc_time_advanced_concurrently": True,
        "full_rhoCentralFoam_time_advance_completed": True,
        "physical_dsmc_wall_flux_sampled_live": True,
        "two_way_feedback_applied_to_continuum": True,
        "adaptive_sampling_surface_completed": True,
        "adaptive_particle_domain_completed": False,
        "synchronized_steps": 1000,
        "coupling_windows": 5,
        "samples_per_window": 40,
        "continuum_adaptive_layer_changes": 112,
        "dsmc_observed_layer_changes": 112,
        "minimum_feedback_scale": 1.0e-5,
        "maximum_feedback_conservation_relative_error": 1.0e-25,
        "maximum_velocity_change_m_per_s": 4.0,
        "maximum_temperature_change_K": 5.0,
        "final_dsmc_parcels": 22000,
        "maximum_live_flux_checksum": 6.0e-6,
        "run_dir": "/project/example/run/gate3e-1",
    }


class Gate3FStaticTest(unittest.TestCase):
    def run_validator(self, data: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate3e.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_gate3e_prerequisite(self) -> None:
        accepted = self.run_validator(valid_gate3e())
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("GATE3E_PREREQUISITE=PASS", accepted.stdout)
        for key, value in (
            ("status", "FAIL"),
            ("adaptive_particle_domain_completed", True),
            ("synchronized_steps", 999),
            ("maximum_feedback_conservation_relative_error", 1.0e-6),
        ):
            record = valid_gate3e()
            record[key] = value
            self.assertNotEqual(self.run_validator(record).returncode, 0, key)

    def test_analyzer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            log = work / "live.log"
            windows = "".join(
                f"GATE3F_WINDOW role=continuum window={window} step={(window + 1) * 200} "
                "feedback_scale=0.1 conservation_rel=1e-20 max_delta_U=1 "
                "max_delta_T=2 adaptive_layer_changes=4\n"
                f"GATE3F_WINDOW role=dsmc window={window} step={(window + 1) * 200} "
                "samples=40 flux_checksum=1e-6 active_layer_changes=4 "
                "active_cells=192 activated_cells=2 deactivated_cells=3 "
                "seeded_parcels=12 removed_parcels=18 inactive_parcels=0 "
                "ownership_balance_error=0 max_overlap_z=0.4\n"
                for window in range(5)
            )
            log.write_text(
                "MUI Rank 0 mpi://continuum/gate3f\n"
                "MUI Rank 1 mpi://dsmc/gate3f\n"
                + windows
                + "GATE3F_PASS role=continuum_live steps=1000 windows=5 "
                "full_rhoCentralFoam_time_advance=true "
                "two_way_feedback_applied=true adaptive_sampling_surface=true "
                "adaptive_layer_changes=4 min_feedback_scale=0.1 "
                "max_conservation_rel=1e-20 max_delta_U=1 max_delta_T=2\n"
                "GATE3F_PASS role=dsmc_live steps=1000 windows=5 "
                "final_parcels=100 inserted=30 active_layer_changes=4 "
                "max_flux_checksum=1e-6 dynamic_activated_cells=2 "
                "deactivated_cells=3 seeded_parcels=12 removed_parcels=18 "
                "retained_identities=900 inactive_parcels=0 "
                "ownership_balance_error=0 max_overlap_z=0.4\n",
                encoding="utf-8",
            )
            summary = work / "summary.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ANALYZER),
                    "--log",
                    str(log),
                    "--summary",
                    str(summary),
                    "--run-dir",
                    str(work),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(summary.read_text(encoding="utf-8"))
            self.assertTrue(record["adaptive_particle_domain_completed"])
            self.assertTrue(
                record["continuum_and_dsmc_time_advanced_concurrently"]
            )
            self.assertEqual(record["maximum_particle_ownership_balance_error"], 0)
            self.assertFalse(record["mesh_topology_changed"])

            mismatch = log.read_text(encoding="utf-8").replace(
                "adaptive_layer_changes=4 min_feedback_scale=0.1",
                "adaptive_layer_changes=5 min_feedback_scale=0.1",
            )
            log.write_text(mismatch, encoding="utf-8")
            rejected = subprocess.run(
                [
                    sys.executable,
                    str(ANALYZER),
                    "--log",
                    str(log),
                    "--summary",
                    str(summary),
                    "--run-dir",
                    str(work),
                ],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_gate3f_header_syntax(self) -> None:
        result = subprocess.run(
            [
                "g++",
                "-std=c++11",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                "-fsyntax-only",
                "-x",
                "c++",
                "-",
                "-I",
                str(ROOT / "tests/stubs"),
                "-I",
                str(ROOT / "include"),
                "-I",
                str(ROOT / "openfoam/gate3c/common"),
                "-I",
                str(ROOT / "openfoam/gate3e/common"),
                "-I",
                str(ROOT / "openfoam/gate3f/common"),
            ],
            input=(
                '#include "Gate3FMui.H"\n'
                "int main() { return gate3f::particleInterfaceRadius(7) > 0 ? 0 : 1; }\n"
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_dynamic_solver_scope(self) -> None:
        dsmc = (
            ROOT / "openfoam/gate3c/dsmcFoamGate3C/dsmcFoamGate3C.C"
        ).read_text()
        runner = (ROOT / "scripts/run_gate3f.sh").read_text()
        self.assertIn("cloud.deleteParticle(parcel)", dsmc)
        self.assertIn("parcel.origProc()", dsmc)
        self.assertIn("seedDynamicCell", dsmc)
        self.assertIn("particleOwnershipBalanceError", dsmc)
        self.assertIn("removeInactiveDynamicParcels", dsmc)
        self.assertIn("rhoCentralFoamGate3F", runner)
        self.assertIn("dsmcFoamGate3F", runner)
        self.assertIn("GATE3F_COMPARISON", runner)


if __name__ == "__main__":
    unittest.main()
