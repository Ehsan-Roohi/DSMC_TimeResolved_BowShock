#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Gate1CStaticTest(unittest.TestCase):
    def test_slurm_spool_uses_exported_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            fake_root = work / "repository"
            runner = fake_root / "scripts/run_gate1c.sh"
            runner.parent.mkdir(parents=True)
            runner.write_text(
                "#!/usr/bin/env bash\nprintf 'SPOOL_ROOT=%s\\n' \"$PWD\"\n",
                encoding="utf-8",
            )
            runner.chmod(0o755)
            spool_copy = work / "slurm-spool-copy.sh"
            spool_copy.write_text(
                (ROOT / "slurm/unity_gate1c.sbatch").read_text(),
                encoding="utf-8",
            )
            elsewhere = work / "compute-working-directory"
            elsewhere.mkdir()
            environment = os.environ.copy()
            environment["GATE1C_ROOT"] = str(fake_root)
            result = subprocess.run(
                ["bash", str(spool_copy)],
                cwd=elsewhere,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.stdout.strip(), f"SPOOL_ROOT={fake_root}")

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
            generated_files = {
                str(path.relative_to(cases))
                for path in cases.rglob("*")
                if path.is_file()
            }
            self.assertEqual(len(generated_files), 44)
            for required in (
                "continuum/0/T",
                "continuum/0/U",
                "continuum/0/p",
                "continuum/constant/momentumTransport",
                "hybrid/0/dsmcRhoN",
                "hybrid/0/fD",
                "hybrid/0/q",
                "reference/0/dsmcRhoN",
                "reference/0/fD",
                "reference/0/q",
            ):
                self.assertIn(required, generated_files)
            self.assertIn("(80 40 1)", (cases / "continuum/system/blockMeshDict").read_text())
            self.assertIn("(40 6 1)", (cases / "hybrid/system/blockMeshDict").read_text())
            self.assertIn("(40 20 1)", (cases / "reference/system/blockMeshDict").read_text())
            continuum_schemes = (cases / "continuum/system/fvSchemes").read_text()
            self.assertIn("div(tauMC) Gauss linear", continuum_schemes)
            self.assertIn("reconstruct(rho) vanLeer", continuum_schemes)
            self.assertIn("reconstruct(U) vanLeerV", continuum_schemes)
            self.assertIn("reconstruct(T) vanLeer", continuum_schemes)
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
            self.assertEqual(result["samples_per_face_observed"], 201)
            self.assertEqual(result["samples_per_face_used"], 200)
            self.assertTrue(result["interface_selected_before_reference"])
            self.assertTrue(comparison.is_file())

            incomplete_hybrid = work / "hybrid_incomplete.log"
            hybrid_lines = hybrid.read_text(encoding="utf-8").splitlines()
            first_sample = next(
                index
                for index, line in enumerate(hybrid_lines)
                if line.startswith("GATE1C_WALL")
            )
            del hybrid_lines[first_sample]
            incomplete_hybrid.write_text(
                "\n".join(hybrid_lines) + "\n", encoding="utf-8"
            )
            incomplete = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_gate1c.py"),
                    "--reference",
                    str(reference),
                    "--hybrid",
                    str(incomplete_hybrid),
                    "--summary",
                    str(work / "incomplete_summary.json"),
                    "--csv",
                    str(work / "incomplete.csv"),
                    "--run-dir",
                    str(cases),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(incomplete.returncode, 0)
            self.assertIn("sampling steps differ", incomplete.stderr)

            shifted_hybrid = work / "hybrid_shifted.log"
            shifted_lines = hybrid.read_text(encoding="utf-8").splitlines()
            later_sample = next(
                index
                for index, line in enumerate(shifted_lines)
                if line.startswith("GATE1C_WALL role=hybrid step=605 face=0 ")
            )
            shifted_lines[later_sample] = shifted_lines[later_sample].replace(
                "x=0.00125 ", "x=0.00126 "
            )
            shifted_hybrid.write_text(
                "\n".join(shifted_lines) + "\n", encoding="utf-8"
            )
            shifted = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_gate1c.py"),
                    "--reference",
                    str(reference),
                    "--hybrid",
                    str(shifted_hybrid),
                    "--summary",
                    str(work / "shifted_summary.json"),
                    "--csv",
                    str(work / "shifted.csv"),
                    "--run-dir",
                    str(cases),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(shifted.returncode, 0)
            self.assertIn("unexpected wall coordinate", shifted.stderr)

    def test_coupling_geometry_contract(self) -> None:
        header = (ROOT / "openfoam/gate1c/common/Gate1CMui.H").read_text()
        self.assertIn("streamwiseCells = 40", header)
        self.assertIn("hybridNormalCells = 6", header)
        self.assertIn("interfaceHeight = 0.015", header)
        self.assertIn("kineticSpan = 0.0025", header)
        solver = (ROOT / "openfoam/gate1c/dsmcFoamGate1C/dsmcFoamGate1C.C").read_text()
        self.assertIn("injectMappedReservoir", solver)
        self.assertIn("GATE1C_WALL", solver)
        self.assertIn("gate1c::fetchState", solver)
        self.assertIn("duplicate_mapped_point", solver)

        runner = (ROOT / "scripts/run_gate1c.sh").read_text()
        self.assertIn("GATE1C_DICTIONARIES_VALIDATED", runner)
        self.assertIn("dictionary_count != 44", runner)
        self.assertIn("GATE1C_PIPELINE_FAIL", runner)
        self.assertIn("--kill-after=30", runner)
        self.assertIn('foamDictionary "$CONTINUUM_CONTROL" -entry startFrom', runner)

        batch = (ROOT / "slurm/unity_gate1c.sbatch").read_text()
        submitter = (ROOT / "scripts/submit_unity_gate1c.sh").read_text()
        self.assertIn("GATE1C_ROOT", batch)
        self.assertIn("SLURM_SUBMIT_DIR", batch)
        self.assertNotIn('dirname "${BASH_SOURCE[0]}"', batch)
        self.assertIn('--export=ALL,GATE1C_ROOT="$ROOT"', submitter)


if __name__ == "__main__":
    unittest.main()
