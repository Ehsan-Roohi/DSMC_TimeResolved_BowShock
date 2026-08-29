from __future__ import annotations

import importlib.util
import json
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ANALYZER_PATH = ROOT / "scripts/analyze_gate3g.py"
SPEC = importlib.util.spec_from_file_location("analyze_gate3g", ANALYZER_PATH)
assert SPEC is not None and SPEC.loader is not None
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def segment_log(name: str, start: int, stop: int) -> str:
    count = (stop - start) // 200
    session = "gate3g_continuous" if name == "continuous" else "gate3g_split"
    continuum_windows = []
    dsmc_windows = []
    for step in range(start + 200, stop + 1, 200):
        window = step // 200 - 1
        continuum_windows.append(
            "GATE3G_WINDOW role=continuum "
            f"segment={name} window={window} step={step} "
            "feedback_scale=0.1 conservation_rel=1e-24 "
            "max_delta_U=1 max_delta_T=2 adaptive_layer_changes=112"
        )
        dsmc_windows.append(
            "GATE3G_WINDOW role=dsmc "
            f"segment={name} window={window} step={step} samples=40 "
            f"flux_checksum={1e-5 * (window + 1)} active_layer_changes=112"
        )
    changes = 112 if start == 0 else 0
    load = (
        "GATE3G_STATE_LOADED step=600 layers=64 accumulators=64\n"
        if start == 600
        else ""
    )
    return (
        f"MUI Rank 0 mpi://continuum/{session}\n"
        f"MUI Rank 1 mpi://dsmc/{session}\n"
        + "\n".join(continuum_windows + dsmc_windows)
        + "\n"
        + load
        + "GATE3G_PASS role=continuum_live "
        + f"segment={name} start_step={start} stop_step={stop} "
        + f"steps={stop-start} first_step={start+1} last_step={stop} "
        + f"windows={count} full_rhoCentralFoam_time_advance=true "
        + "two_way_feedback_applied=true adaptive_sampling_surface=true "
        + f"adaptive_layer_changes={changes} min_feedback_scale=0.1 "
        + "max_conservation_rel=1e-24 max_delta_U=1 max_delta_T=2\n"
        + "GATE3G_STATE_WRITTEN step="
        + f"{stop} layers=64 accumulators=64\n"
        + "GATE3G_PASS role=dsmc_live "
        + f"segment={name} start_step={start} stop_step={stop} "
        + f"steps={stop-start} first_step={start+1} last_step={stop} "
        + f"windows={count} final_parcels=6000 inserted=100 "
        + f"active_layer_changes={changes} max_flux_checksum=5e-5 "
        + "dynamic_activated_cells=1 deactivated_cells=52 "
        + "seeded_parcels=66 removed_parcels=100 retained_identities=1000 "
        + "inactive_parcels=0 ownership_balance_error=0 max_overlap_z=0.3 "
        + "checkpoint_written=true\n"
    )


class Gate3GTest(unittest.TestCase):
    def test_analyzer_accepts_exact_step_coverage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            continuous = root / "continuous.log"
            fresh = root / "fresh.log"
            restart = root / "restart.log"
            checkpoint = root / "checkpoint.state"
            continuous.write_text(segment_log("continuous", 0, 1000))
            fresh.write_text(segment_log("fresh", 0, 600))
            restart.write_text(segment_log("restart", 600, 1000))
            checkpoint.write_text(
                "GATE3G_STATE_V1 600 64\n" + "6 0\n" * 64
            )
            scaling = []
            for ranks, wall in ((1, 4.0), (2, 2.2), (4, 1.3)):
                path = root / f"scaling_{ranks}.log"
                path.write_text(
                    f"GATE3G_SCALING ranks={ranks} iterations=250000 "
                    f"wall_seconds={wall} checksum=12345 "
                    "ownership_balance_error=0\n"
                )
                scaling.append(path)
            summary = ANALYZER.analyze(
                continuous, fresh, restart, checkpoint, scaling, str(root)
            )
            self.assertEqual(summary["status"], "PASS")
            self.assertTrue(
                summary["restart_has_no_duplicated_or_missing_coupling_step"]
            )
            self.assertFalse(summary["restart_matches_continuous_byte_for_byte"])

    def test_analyzer_rejects_restart_gap(self) -> None:
        text = segment_log("restart", 600, 1000).replace(
            "first_step=601", "first_step=602", 1
        )
        with self.assertRaisesRegex(ValueError, "first step"):
            ANALYZER.validate_segment(text, "restart", 600, 1000, 2)

    def test_source_declares_recovery_contract(self) -> None:
        continuum = (
            ROOT / "openfoam/gate1b/rhoCentralFoamMUI/rhoCentralFoamMUI.C"
        ).read_text()
        dsmc = (
            ROOT / "openfoam/gate3c/dsmcFoamGate3C/dsmcFoamGate3C.C"
        ).read_text()
        runner = (ROOT / "scripts/run_gate3g.sh").read_text()
        self.assertIn("GATE3G_START_STEP", continuum)
        self.assertIn("GATE3G_STOP_STEP", continuum)
        self.assertIn("GATE3G_STATE_V1", dsmc)
        self.assertIn("GATE3G_STATE_LOADED", dsmc)
        self.assertIn("run_pair restart 600 1000", runner)
        self.assertIn("gate3g_scaling_4.log", runner)

    def test_dsmc_wrapper_includes_openfoam_solver_headers(self) -> None:
        options = (
            ROOT / "openfoam/gate3g/dsmcFoamGate3G/Make/options"
        ).read_text()
        self.assertIn(
            "-I$(FOAM_APP)/solvers/discreteMethods/dsmc/dsmcFoam",
            options,
        )
        self.assertLess(options.index("-lfiniteVolume"), options.index("-lDSMC"))

    def test_gate3f_result_validator(self) -> None:
        result = ROOT / "docs/results/gate3f_unity_63702483.json"
        if not result.exists():
            self.skipTest("immutable result is added with Gate 3G documentation")
        completed = subprocess.run(
            ["python3", str(ROOT / "scripts/require_gate3f_pass.py"), str(result)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_json_contract_is_serializable(self) -> None:
        payload = {
            "gate": "3G-LIVE-COUPLED-RESTART",
            "restart_step_boundary": 600,
            "scaling_rank_counts": [1, 2, 4],
        }
        self.assertEqual(json.loads(json.dumps(payload)), payload)


if __name__ == "__main__":
    unittest.main()
