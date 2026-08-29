from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ANALYZER_PATH = ROOT / "scripts/analyze_gate3h.py"
SPEC = importlib.util.spec_from_file_location("analyze_gate3h", ANALYZER_PATH)
assert SPEC is not None and SPEC.loader is not None
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def scaling_log(replicas: int, wall: float) -> str:
    lines: list[str] = []
    for replica in range(replicas):
        segment = f"scale_{replicas}_{replica}"
        lines.extend(
            [
                "GATE3G_PASS role=continuum_live "
                f"segment={segment} start_step=0 stop_step=400 steps=400 "
                "first_step=1 last_step=400 windows=2 "
                "full_rhoCentralFoam_time_advance=true "
                "two_way_feedback_applied=true adaptive_sampling_surface=true "
                "adaptive_layer_changes=112 min_feedback_scale=0.1 "
                "max_conservation_rel=1e-24 max_delta_U=1 max_delta_T=2",
                "GATE3G_PASS role=dsmc_live "
                f"segment={segment} start_step=0 stop_step=400 steps=400 "
                "first_step=1 last_step=400 windows=2 final_parcels=6400 "
                "inserted=100 active_layer_changes=112 max_flux_checksum=5e-6 "
                "dynamic_activated_cells=1 deactivated_cells=52 "
                "seeded_parcels=66 removed_parcels=100 retained_identities=1000 "
                "inactive_parcels=0 ownership_balance_error=0 max_overlap_z=0.3 "
                "checkpoint_written=true",
            ]
        )
    lines.append(
        f"GATE3H_SCALING replicas={replicas} solver_ranks={2*replicas} "
        f"steps_per_replica=400 wall_seconds={wall}"
    )
    return "\n".join(lines) + "\n"


class Gate3HTest(unittest.TestCase):
    def test_analyzer_accepts_complete_full_solver_inventory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            logs = []
            for replicas, wall in ((1, 10.0), (2, 10.5), (4, 11.0)):
                path = root / f"scaling_{replicas}.log"
                path.write_text(scaling_log(replicas, wall), encoding="utf-8")
                logs.append(path)
            summary = ANALYZER.analyze(logs, str(root))
            self.assertEqual(summary["status"], "PASS")
            self.assertTrue(summary["full_solver_parallel_scaling_completed"])
            self.assertFalse(summary["domain_decomposition_completed"])
            self.assertEqual(summary["total_solver_rank_counts"], [2, 4, 8])

    def test_analyzer_rejects_missing_replica(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            logs = []
            for replicas, wall in ((1, 10.0), (2, 10.5), (4, 11.0)):
                text = scaling_log(replicas, wall)
                if replicas == 4:
                    text = text.replace(
                        "GATE3G_PASS role=dsmc_live segment=scale_4_3",
                        "GATE3G_SKIP role=dsmc_live segment=scale_4_3",
                    )
                path = root / f"scaling_{replicas}.log"
                path.write_text(text, encoding="utf-8")
                logs.append(path)
            with self.assertRaisesRegex(ValueError, "replica inventory"):
                ANALYZER.analyze(logs, str(root))

    def test_runner_launches_full_solver_pairs(self) -> None:
        runner = (ROOT / "scripts/run_gate3h.sh").read_text(encoding="utf-8")
        self.assertIn("for replicas in 1 2 4", runner)
        self.assertIn("rhoCentralFoamGate3G", runner)
        self.assertIn("dsmcFoamGate3G", runner)
        self.assertIn("GATE3G_STOP_STEP=400", runner)
        self.assertIn("GATE3H_SCALING replicas=", runner)
        self.assertNotIn("-parallel", runner)

    def test_gate3g_result_validator(self) -> None:
        result = ROOT / "docs/results/gate3g_unity_63737420.json"
        completed = subprocess.run(
            ["python3", str(ROOT / "scripts/require_gate3g_pass.py"), str(result)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
