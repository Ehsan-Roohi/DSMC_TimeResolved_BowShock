#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SETTER = ROOT / "scripts/set_openfoam_start_time.py"


class Gate2TimePrecisionTest(unittest.TestCase):
    def test_unity_snapshot_names_are_preserved_exactly(self) -> None:
        snapshots = (
            "0",
            "2.498730336e-05",
            "4.998730336e-05",
            "7.498730336e-05",
            "9.998730336e-05",
        )
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "controlDict"
            control.write_text(
                "startFrom startTime;\n"
                "startTime       0;\n"
                "timePrecision   10;\n",
                encoding="utf-8",
            )
            for snapshot in snapshots:
                result = subprocess.run(
                    [sys.executable, str(SETTER), str(control), snapshot],
                    check=True,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(
                    result.stdout.strip(), f"GATE2_START_TIME={snapshot}"
                )
                self.assertIn(
                    f"startTime       {snapshot};",
                    control.read_text(encoding="utf-8"),
                )

    def test_ambiguous_or_unsafe_start_time_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control = Path(directory) / "controlDict"
            original = "startTime 0;\nstartTime 1;\n"
            control.write_text(original, encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SETTER), str(control), "2.5e-05;rm"],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(control.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
