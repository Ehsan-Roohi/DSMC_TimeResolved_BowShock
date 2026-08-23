#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Gate1CStaticTest(unittest.TestCase):
    def test_case_generation_and_analysis_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            cases = work / "cases"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/generate_gate1c_cases.py"), str(cases)],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("(80 40 1)", (cases / "continuum/system/blockMeshDict").read_text())
            self.assertIn("(40 6 1)", (cases / "hybrid/system/blockMeshDict").read_text())
            self.assertIn("(40 20 1)", (cases / "reference/system/blockMeshDict").read_text())
            self.assertIn(
                "InflowBoundaryModel none",
                (cases / "hybrid/constant/dsmcProperties").read_text(),
            )
            self.assertIn(
                "FreeStreamCoeffs",
                (cases / "reference/constant/dsmcProperties").read_text(),
            )

            reference = work / "reference.log"
            hybrid = work / "hybrid.log"
            with reference.open("w", encoding="utf-8") as ref_stream, hybrid.open(
                "w", encoding="utf-8"
            ) as hybrid_stream:
                for step in range(600, 1601, 5):
                    for face in range(40):
                        x = (face + 0.5) * 0.0025
                        q = 1000.0 + 2.0 * face + (step % 20)
                        tau = 10.0 + 0.1 * face + 0.01 * (step % 20)
                        ref_stream.write(
                            f"GATE1C_WALL role=reference step={step} face={face} "
                            f"x={x} q={q} tau={tau}\n"
                        )
                        hybrid_stream.write(
                            f"GATE1C_WALL role=hybrid step={step} face={face} "
                            f"x={x} q={1.01*q} tau={1.01*tau}\n"
                        )
                ref_stream.write("GATE1C_PASS role=reference steps=1600\n")
                hybrid_stream.write("GATE1C_PASS role=hybrid steps=1600\n")

            summary = work / "summary.json"
            comparison = work / "comparison.csv"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_gate1c.py"),
                    "--reference",
                    str(reference),
                    "--hybrid",
                    str(hybrid),
                    "--summary",
                    str(summary),
                    "--csv",
                    str(comparison),
                    "--run-dir",
                    str(cases),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            result = json.loads(summary.read_text())
            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["wall_faces"], 40)
            self.assertEqual(result["samples_per_face_used"], 200)
            self.assertTrue(result["interface_selected_before_reference"])
            self.assertTrue(comparison.is_file())

    def test_coupling_geometry_contract(self) -> None:
        header = (ROOT / "openfoam/gate1c/common/Gate1CMui.H").read_text()
        self.assertIn("streamwiseCells = 40", header)
        self.assertIn("hybridNormalCells = 6", header)
        self.assertIn("interfaceHeight = 0.015", header)
        solver = (ROOT / "openfoam/gate1c/dsmcFoamGate1C/dsmcFoamGate1C.C").read_text()
        self.assertIn("injectMappedReservoir", solver)
        self.assertIn("GATE1C_WALL", solver)
        self.assertIn("gate1c::fetchState", solver)


if __name__ == "__main__":
    unittest.main()
