from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts/require_gate3b_pilot_pass.py"


def valid_pilot() -> dict[str, object]:
    return {
        "gate": "3B-PILOT",
        "status": "PASS",
        "transport": "MUI-MPMD",
        "resolutions": ["coarse", "medium", "fine"],
        "activated_layer_events": 6,
        "deactivated_layer_events": 6,
        "maximum_raw_rbf_conservation_relative_error": 8.1e-7,
        "maximum_allowed_raw_rbf_conservation_relative_error": 0.2,
        "maximum_mapped_conservation_relative_error": 1.5e-16,
        "maximum_relaxed_conservation_relative_error": 6.3e-16,
        "maximum_moving_boundary_conservation_relative_error": 6.3e-16,
        "conservation_tolerance": 1.0e-8,
        "restart_matches_continuous_byte_for_byte": True,
    }


class Gate3CStaticTest(unittest.TestCase):
    def run_validator(self, data: dict[str, object]) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "pilot.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_gate3b_pilot_prerequisite(self) -> None:
        accepted = self.run_validator(valid_pilot())
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("GATE3B_PILOT_PREREQUISITE=PASS", accepted.stdout)
        for key, value in (
            ("status", "FAIL"),
            ("restart_matches_continuous_byte_for_byte", False),
            ("activated_layer_events", 0),
            ("maximum_moving_boundary_conservation_relative_error", 2.0e-8),
        ):
            record = valid_pilot()
            record[key] = value
            self.assertNotEqual(self.run_validator(record).returncode, 0, key)

    def test_case_generation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cases = Path(directory) / "cases"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/generate_gate3c_cases.py"), str(cases)],
                check=True,
                capture_output=True,
                text=True,
            )
            files = [path for path in cases.rglob("*") if path.is_file()]
            self.assertEqual(len(files), 44)
            continuum_mesh = (cases / "continuum/system/blockMeshDict").read_text()
            hybrid_mesh = (cases / "hybrid/system/blockMeshDict").read_text()
            reference_mesh = (cases / "reference/system/blockMeshDict").read_text()
            self.assertEqual(continuum_mesh.count("    hex ("), 8)
            self.assertEqual(hybrid_mesh.count("    hex ("), 8)
            self.assertEqual(reference_mesh.count("    hex ("), 8)
            self.assertIn("(32 8 1)", continuum_mesh)
            self.assertIn("(6 8 1)", hybrid_mesh)
            self.assertIn("(16 8 1)", reference_mesh)
            self.assertIn("    interface\n", hybrid_mesh)
            self.assertNotIn("farfieldInlet", hybrid_mesh)
            self.assertIn("farfieldInlet", reference_mesh)
            self.assertIn("farfieldOutlet", reference_mesh)
            self.assertIn(
                "InflowBoundaryModel none",
                (cases / "hybrid/constant/dsmcProperties").read_text(),
            )
            self.assertIn(
                "InflowBoundaryModel FreeStream",
                (cases / "reference/constant/dsmcProperties").read_text(),
            )

    def test_analysis_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            reference = work / "reference.log"
            hybrid = work / "hybrid.log"
            with reference.open("w", encoding="utf-8") as ref, hybrid.open(
                "w", encoding="utf-8"
            ) as hyb:
                for step in range(600, 1601, 5):
                    for face in range(64):
                        theta = (face + 0.5) * 2.0 * 3.141592653589793 / 64.0
                        q = 1000.0 + 3.0 * face + (step % 20)
                        drag = 20.0 + 0.2 * face + 0.01 * (step % 20)
                        lift = 0.1 * face
                        area = 2.5e-6
                        ref.write(
                            f"GATE3C_WALL role=reference step={step} face={face} "
                            f"theta={theta} area={area} q={q} drag={drag} lift={lift}\n"
                        )
                        hyb.write(
                            f'GATE3C_WALL role="hybrid" step={step} face={face} '
                            f"theta={theta} area={area} q={1.01*q} "
                            f"drag={1.01*drag} lift={lift}\n"
                        )
                ref.write("GATE3C_PASS role=reference steps=1600\n")
                hyb.write('GATE3C_PASS role="hybrid" steps=1600\n')
            summary = work / "summary.json"
            comparison = work / "comparison.csv"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_gate3c.py"),
                    "--reference", str(reference),
                    "--hybrid", str(hybrid),
                    "--summary", str(summary),
                    "--csv", str(comparison),
                    "--run-dir", str(work),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("GATE3C_PHYSICAL_PREFLIGHT_STATUS=PASS", result.stdout)
            record = json.loads(summary.read_text())
            self.assertEqual(record["wall_faces"], 64)
            self.assertEqual(record["samples_per_face_used"], 200)
            self.assertFalse(record["two_way_flux_applied_to_continuum"])
            self.assertTrue(comparison.is_file())

    def test_solver_and_runner_scope_guards(self) -> None:
        header = (ROOT / "openfoam/gate3c/common/Gate3CMui.H").read_text()
        solver = (ROOT / "openfoam/gate3c/dsmcFoamGate3C/dsmcFoamGate3C.C").read_text()
        runner = (ROOT / "scripts/run_gate3c.sh").read_text()
        analyzer = (ROOT / "scripts/analyze_gate3c.py").read_text()
        self.assertIn("angularCells = 64", header)
        self.assertIn("interfaceRadius = 0.025", header)
        self.assertIn("injectMappedReservoir", solver)
        self.assertIn("GATE3C_WALL", solver)
        self.assertIn("GATE3C_DICTIONARIES_VALIDATED", runner)
        self.assertIn("dictionary_count != 44", runner)
        self.assertIn("GATE3C_REFERENCE_RUN_ORDER=3", runner)
        self.assertIn("gate3b_pilot_summary.json", runner)
        self.assertIn('"two_way_flux_applied_to_continuum": False', analyzer)
        self.assertIn('"parallel_scaling_completed": False', analyzer)


if __name__ == "__main__":
    unittest.main()
