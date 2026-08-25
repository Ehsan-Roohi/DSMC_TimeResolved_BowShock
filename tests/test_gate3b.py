import json
import pathlib
import subprocess
import sys
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "scripts" / "require_gate3a_pass.py"


def valid_artifact():
    return {
        "gate": "3A",
        "status": "PASS",
        "transport": "MUI-MPMD",
        "windows": 3,
        "unresolved_window_skipped": True,
        "maximum_raw_rbf_conservation_relative_error": 0.017,
        "maximum_allowed_raw_rbf_conservation_relative_error": 0.05,
        "maximum_mapped_conservation_relative_error": 0.0,
        "maximum_relaxed_conservation_relative_error": 2.5e-16,
        "conservation_tolerance": 1.0e-8,
        "restart_matches_continuous_byte_for_byte": True,
    }


class Gate3BPrerequisiteTest(unittest.TestCase):
    def run_validator(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / "gate3a.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(VALIDATOR), str(path)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )

    def test_accepts_verified_gate3a(self):
        result = self.run_validator(valid_artifact())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("GATE3A_PREREQUISITE=PASS", result.stdout)

    def test_rejects_failed_status(self):
        data = valid_artifact()
        data["status"] = "FAIL"
        self.assertNotEqual(self.run_validator(data).returncode, 0)

    def test_rejects_unbounded_raw_rbf_defect(self):
        data = valid_artifact()
        data["maximum_raw_rbf_conservation_relative_error"] = 0.051
        self.assertNotEqual(self.run_validator(data).returncode, 0)

    def test_rejects_projected_conservation_failure(self):
        data = valid_artifact()
        data["maximum_mapped_conservation_relative_error"] = 2.0e-8
        self.assertNotEqual(self.run_validator(data).returncode, 0)

    def test_rejects_restart_mismatch(self):
        data = valid_artifact()
        data["restart_matches_continuous_byte_for_byte"] = False
        self.assertNotEqual(self.run_validator(data).returncode, 0)


if __name__ == "__main__":
    unittest.main()
