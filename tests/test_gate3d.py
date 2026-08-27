from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/require_gate3c_pass.py"
ANALYZER = ROOT / "scripts/analyze_gate3d.py"


def valid_gate3c() -> dict[str, object]:
    return {
        "gate": "3C-PHYSICAL-PREFLIGHT",
        "status": "PASS",
        "openfoam_version": "v2312",
        "coupling": "one-way-fixed-radius-continuum-to-dsmc-via-MUI",
        "interface_selected_before_reference": True,
        "full_dsmc_executed_after_hybrid": True,
        "wall_faces": 64,
        "samples_per_face_used": 200,
        "heat_flux_pass": True,
        "drag_pass": True,
        "heat_flux_normalized_l2": 0.12,
        "heat_flux_acceptance_threshold": 0.20,
        "drag_density_normalized_l2": 0.08,
        "drag_acceptance_threshold": 0.16,
        "total_drag_relative_error": 0.018,
        "two_way_flux_applied_to_continuum": False,
        "adaptive_interface_completed": False,
        "parallel_scaling_completed": False,
    }


class Gate3DStaticTest(unittest.TestCase):
    def run_validator(self, data: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gate3c.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_gate3c_prerequisite(self) -> None:
        accepted = self.run_validator(valid_gate3c())
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("GATE3C_PHYSICAL_PREREQUISITE=PASS", accepted.stdout)
        for key, value in (
            ("status", "FAIL"),
            ("heat_flux_pass", False),
            ("total_drag_relative_error", 0.051),
            ("two_way_flux_applied_to_continuum", True),
        ):
            record = valid_gate3c()
            record[key] = value
            self.assertNotEqual(self.run_validator(record).returncode, 0, key)

    def test_analyzer_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            continuous = work / "continuous.log"
            fresh = work / "fresh.log"
            restart = work / "restart.log"
            feedback = work / "feedback.log"
            continuous.write_text(
                "GATE3D_PASS role=dsmc_replay mode=continuous windows=5\n"
                "GATE3D_PASS role=continuum mode=continuous "
                "two_way_feedback_received=true adaptive_interface=true "
                "activated_layers=3 deactivated_layers=5 "
                "max_raw_conservation_rel=1e-16 "
                "max_projected_conservation_rel=0 "
                "max_relaxed_conservation_rel=2e-16 last_window=4\n",
                encoding="utf-8",
            )
            fresh.write_text(
                "GATE3D_PASS role=dsmc_replay mode=fresh windows=3\n"
                "GATE3D_PASS role=continuum mode=fresh activated_layers=2 "
                "deactivated_layers=4 max_raw_conservation_rel=1e-16 "
                "max_projected_conservation_rel=0 max_relaxed_conservation_rel=2e-16\n",
                encoding="utf-8",
            )
            restart.write_text(
                "GATE3D_PASS role=dsmc_replay mode=restart windows=2\n"
                "GATE3D_PASS role=continuum mode=restart activated_layers=1 "
                "deactivated_layers=1 max_raw_conservation_rel=1e-16 "
                "max_projected_conservation_rel=0 max_relaxed_conservation_rel=2e-16\n",
                encoding="utf-8",
            )
            feedback.write_text(
                "GATE3D_PASS role=continuum_feedback fields_written=true "
                "target_time=0.0001 faces=64 feedback_scale=1e-4 "
                "applied_momentum_x=-1e-8 applied_momentum_y=0 "
                "applied_momentum_z=0 applied_energy=-2e-6 "
                "conservation_rel=0 max_delta_U=0.1 max_delta_T=0.2\n",
                encoding="utf-8",
            )
            state = b"deterministic-state\n"
            csv = b"deterministic-csv\n"
            for name in ("continuous.state", "resumed.state"):
                (work / name).write_bytes(state)
            for name in ("continuous.csv", "resumed.csv"):
                (work / name).write_bytes(csv)
            scaling_paths = []
            for ranks, seconds in ((1, 0.30), (2, 0.20), (4, 0.15)):
                path = work / f"scaling-{ranks}.log"
                path.write_text(
                    f"GATE3D_SCALING ranks={ranks} iterations=20000 "
                    f"wall_seconds={seconds} mass=0 momentum_x=1e-8 "
                    "momentum_y=0 momentum_z=0 energy=2e-6 sink=0\n",
                    encoding="utf-8",
                )
                scaling_paths.append(path)
            summary = work / "summary.json"
            command = [
                sys.executable,
                str(ANALYZER),
                "--continuous-log", str(continuous),
                "--fresh-log", str(fresh),
                "--restart-log", str(restart),
                "--feedback-log", str(feedback),
                "--continuous-state", str(work / "continuous.state"),
                "--resumed-state", str(work / "resumed.state"),
                "--continuous-csv", str(work / "continuous.csv"),
                "--resumed-csv", str(work / "resumed.csv"),
                "--summary", str(summary),
                "--run-dir", str(work),
            ]
            for path in scaling_paths:
                command.extend(("--scaling-log", str(path)))
            result = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(summary.read_text(encoding="utf-8"))
            self.assertEqual(record["status"], "PASS")
            self.assertTrue(record["two_way_flux_applied_to_continuum"])
            self.assertTrue(record["adaptive_interface_completed"])
            self.assertTrue(record["parallel_scaling_completed"])
            self.assertFalse(record["live_concurrent_openfoam_dsmc_completed"])

    def test_scope_guards(self) -> None:
        source = (ROOT / "src/gate3d/mui_physical_feedback.cpp").read_text()
        feedback = (
            ROOT
            / "openfoam/gate3d/gate3dContinuumFeedback/gate3dContinuumFeedback.C"
        ).read_text()
        runner = (ROOT / "scripts/run_gate3d.sh").read_text()
        analyzer = (ROOT / "scripts/analyze_gate3d.py").read_text()
        self.assertIn("physicalIntegratedFlux", source)
        self.assertIn("limitedInterfaceTransition", source)
        self.assertIn("projectGlobalConservation", source)
        self.assertIn("pressure.write()", feedback)
        self.assertIn("temperature.write()", feedback)
        self.assertIn("velocity.write()", feedback)
        self.assertIn("for ranks in 1 2 4", runner)
        self.assertIn('"live_concurrent_openfoam_dsmc_completed": False', analyzer)

    def test_mui_source_syntax(self) -> None:
        result = subprocess.run(
            [
                "g++",
                "-std=c++11",
                "-Wall",
                "-Wextra",
                "-Wpedantic",
                "-Werror",
                "-fsyntax-only",
                "-I", str(ROOT / "tests/stubs"),
                "-I", str(ROOT / "include"),
                str(ROOT / "src/gate3d/mui_physical_feedback.cpp"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
