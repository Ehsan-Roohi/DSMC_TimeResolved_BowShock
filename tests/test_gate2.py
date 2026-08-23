#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Gate2StaticTest(unittest.TestCase):
    def test_gate1c_prerequisite_validation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            record = {
                "gate": "1C",
                "status": "PASS",
                "interface_selected_before_reference": True,
                "full_dsmc_executed_after_hybrid": True,
                "heat_flux_pass": True,
                "shear_pass": True,
            }
            summary = work / "gate1c.json"
            summary.write_text(json.dumps(record), encoding="utf-8")
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/require_gate1c_pass.py"), str(summary)],
                check=True,
            )
            record["heat_flux_pass"] = False
            summary.write_text(json.dumps(record), encoding="utf-8")
            rejected = subprocess.run(
                [sys.executable, str(ROOT / "scripts/require_gate1c_pass.py"), str(summary)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn("heat_flux_pass", rejected.stderr)

    def test_case_generation_contract(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            cases = Path(directory) / "cases"
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/generate_gate2_cases.py"), str(cases)],
                check=True,
                capture_output=True,
                text=True,
            )
            files = [path for path in cases.rglob("*") if path.is_file()]
            self.assertEqual(len(files), 28)
            self.assertIn(
                "purgeWrite          0;",
                (cases / "continuum/system/controlDict").read_text(),
            )
            properties = (cases / "adaptive/system/gate2Properties").read_text()
            self.assertIn("activationThreshold     0.05;", properties)
            self.assertIn("deactivationThreshold   0.03;", properties)
            self.assertIn("minimumLayers           1;", properties)
            self.assertIn("haloLayers              1;", properties)
            self.assertIn("(80 40 1)", (cases / "continuum/system/blockMeshDict").read_text())
            self.assertIn("(40 20 1)", (cases / "adaptive/system/blockMeshDict").read_text())

    def test_analyzer_requires_complete_reference_free_transition_audit(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            indicator = work / "indicator.csv"
            with indicator.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(
                    ["frame", "time", "cell", "i", "j", "x", "y", "indicator",
                     "n", "ux", "uy", "uz", "T"]
                )
                for frame in range(9):
                    for cell in range(800):
                        i, j = cell % 40, cell // 40
                        writer.writerow(
                            [frame, frame, cell, i, j, (i + 0.5) * 0.0025,
                             (j + 0.5) * 0.0025, 0.06 if j < 2 else 0.0,
                             1.0e20, 1500.0, 0.0, 0.0, 300.0]
                        )

            log = work / "manager.log"
            rows = []
            for frame in range(9):
                activated = 40 if frame in (0, 1) else 0
                deactivated = 40 if frame == 5 else 0
                retained = 40 if frame == 0 else 80 if frame < 5 else 40
                active = 80 if 1 <= frame < 5 else 40
                rows.append(
                    f"GATE2_FRAME frame={frame} active={active} min_layers=1 "
                    f"max_layers={2 if active == 80 else 1} activated={activated} "
                    f"deactivated={deactivated} retained={retained} "
                    f"reused_parcels={retained * 36} "
                    f"created_parcels={activated * 36} inactive_parcels=0 "
                    "max_overlap_z=0.2"
                )
            rows.append(
                "GATE2_PASS role=particle_manager frames=9 "
                "activation_threshold=0.05 deactivation_threshold=0.03 "
                "dynamic_activated=40 deactivated=40 retained=560 "
                "max_overlap_z=0.2 external_reference_used=false"
            )
            log.write_text("\n".join(rows) + "\n", encoding="utf-8")
            summary = work / "summary.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_gate2.py"),
                    "--log", str(log),
                    "--indicator", str(indicator),
                    "--summary", str(summary),
                    "--run-dir", str(work),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertIn("GATE2_STATUS=PASS", result.stdout)
            record = json.loads(summary.read_text())
            self.assertEqual(record["status"], "PASS")
            self.assertTrue(record["particle_identity_reuse"])
            self.assertFalse(record["external_reference_used"])
            self.assertEqual(record["frames"], 9)

            bad = log.read_text().replace(
                "external_reference_used=false", "external_reference_used=true"
            )
            log.write_text(bad, encoding="utf-8")
            rejected = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/analyze_gate2.py"),
                    "--log", str(log),
                    "--indicator", str(indicator),
                    "--summary", str(work / "bad.json"),
                    "--run-dir", str(work),
                ],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(rejected.returncode, 0)

    def test_openfoam_and_runner_contracts(self) -> None:
        indicator = (
            ROOT / "openfoam/gate2/gate2ContinuumIndicator/gate2ContinuumIndicator.C"
        ).read_text()
        manager = (
            ROOT / "openfoam/gate2/gate2ParticleManager/gate2ParticleManager.C"
        ).read_text()
        runner = (ROOT / "scripts/run_gate2.sh").read_text()
        self.assertIn("knDensity", indicator)
        self.assertIn("knTemperature", indicator)
        self.assertIn("knVelocity", indicator)
        self.assertIn("activationThreshold", manager)
        self.assertIn("deactivationThreshold", manager)
        self.assertIn("dsmc.deleteParticle(parcel)", manager)
        self.assertIn("parcel.origId()", manager)
        self.assertIn("newlyActivated[logical]", manager)
        self.assertIn("external_reference_used=false", manager)
        self.assertNotIn("reference", runner.lower())
        self.assertIn("dictionary_count != 28", runner)
        self.assertIn("wc -l <\"$INDICATOR_CSV\") -ne 7201", runner)
        self.assertIn("GATE2_PIPELINE_FAIL", runner)
        self.assertIn("--kill-after=30", runner)

    def test_slurm_spool_uses_exported_repository_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            fake_root = work / "repository"
            runner = fake_root / "scripts/run_gate2.sh"
            runner.parent.mkdir(parents=True)
            runner.write_text(
                "#!/usr/bin/env bash\nprintf 'SPOOL_ROOT=%s\\n' \"$PWD\"\n",
                encoding="utf-8",
            )
            runner.chmod(0o755)
            spool_copy = work / "slurm-spool-copy.sh"
            spool_copy.write_text(
                (ROOT / "slurm/unity_gate2.sbatch").read_text(),
                encoding="utf-8",
            )
            elsewhere = work / "compute-working-directory"
            elsewhere.mkdir()
            environment = os.environ.copy()
            environment["GATE2_ROOT"] = str(fake_root)
            result = subprocess.run(
                ["bash", str(spool_copy)],
                cwd=elsewhere,
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.stdout.strip(), f"SPOOL_ROOT={fake_root}")


if __name__ == "__main__":
    unittest.main()
