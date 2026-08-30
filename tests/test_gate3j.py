from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ANALYZER_PATH = ROOT / "scripts/analyze_gate3j.py"
SPEC = importlib.util.spec_from_file_location("analyze_gate3j", ANALYZER_PATH)
assert SPEC is not None and SPEC.loader is not None
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def live_log() -> str:
    return "\n".join(
        [
            "GATE3J_LAYOUT continuum_ranks=2 dsmc_ranks=2 total_ranks=4 worlds=2",
            "MUI Rank 0 mpi://continuum/gate3j",
            "MUI Rank 2 mpi://dsmc/gate3j",
            "GATE3G_PASS role=continuum_live segment=gate3j start_step=0 "
            "stop_step=200 steps=200 first_step=1 last_step=200 windows=1 "
            "full_rhoCentralFoam_time_advance=true two_way_feedback_applied=true "
            "adaptive_sampling_surface=true adaptive_layer_changes=10 "
            "min_feedback_scale=0.2 max_conservation_rel=1e-24 "
            "max_delta_U=1 max_delta_T=2",
            "GATE3G_PASS role=dsmc_live segment=gate3j start_step=0 "
            "stop_step=200 steps=200 first_step=1 last_step=200 windows=1 "
            "final_parcels=6400 inserted=100 active_layer_changes=10 "
            "max_flux_checksum=5e-6 dynamic_activated_cells=1 "
            "deactivated_cells=0 seeded_parcels=66 removed_parcels=100 "
            "retained_identities=1000 inactive_parcels=0 "
            "ownership_balance_error=0 max_overlap_z=0.3 "
            "checkpoint_written=true",
            "GATE3J_PASS role=continuum_distributed spatial_ranks=2 "
            "unique_interface_ownership=true full_rhoCentralFoam_time_advance=true "
            "two_way_feedback_applied=true",
            "GATE3J_PASS role=dsmc_distributed spatial_ranks=2 "
            "global_final_parcels=6400 global_interface_ownership=true "
            "global_wall_flux_reduction=true full_dsmcFoam_time_advance=true",
        ]
    ) + "\n"


class Gate3JTest(unittest.TestCase):
    def test_analyzer_accepts_live_distributed_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            live = root / "live.log"
            decomposition = root / "decomposition.log"
            live.write_text(live_log(), encoding="utf-8")
            decomposition.write_text(
                "GATE3J_DECOMPOSITION role=continuum spatial_ranks=2 "
                "fields=true mesh_ok=true\n"
                "GATE3J_DECOMPOSITION role=dsmc spatial_ranks=2 "
                "fields=true mesh_ok=true\n",
                encoding="utf-8",
            )
            summary = ANALYZER.analyze(live, decomposition, str(root))
            self.assertEqual(summary["status"], "PASS")
            self.assertTrue(summary["live_distributed_openfoam_dsmc_completed"])
            self.assertFalse(summary["distributed_checkpoint_restart_completed"])

    def test_analyzer_rejects_missing_distributed_role(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            live = root / "live.log"
            decomposition = root / "decomposition.log"
            live.write_text(
                live_log().replace(
                    "GATE3J_PASS role=dsmc_distributed",
                    "GATE3J_SKIP role=dsmc_distributed",
                ),
                encoding="utf-8",
            )
            decomposition.write_text(
                "GATE3J_DECOMPOSITION role=continuum spatial_ranks=2 "
                "fields=true mesh_ok=true\n"
                "GATE3J_DECOMPOSITION role=dsmc spatial_ranks=2 "
                "fields=true mesh_ok=true\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "dsmc_distributed"):
                ANALYZER.analyze(live, decomposition, str(root))

    def test_runner_uses_full_fields_subworlds_and_real_solvers(self) -> None:
        runner = (ROOT / "scripts/run_gate3j.sh").read_text(encoding="utf-8")
        self.assertIn("decomposePar -case", runner)
        self.assertNotIn("-no-fields", runner)
        self.assertIn("rhoCentralFoamGate3J", runner)
        self.assertIn("dsmcFoamGate3J", runner)
        self.assertIn("-parallel -world continuum", runner)
        self.assertIn("-parallel -world dsmc", runner)
        self.assertIn("GATE3G_STOP_STEP=200", runner)

    def test_solvers_enable_distributed_ownership_code(self) -> None:
        continuum = (
            ROOT / "openfoam/gate3j/rhoCentralFoamGate3J/rhoCentralFoamGate3J.C"
        ).read_text(encoding="utf-8")
        dsmc = (
            ROOT / "openfoam/gate3j/dsmcFoamGate3J/dsmcFoamGate3J.C"
        ).read_text(encoding="utf-8")
        base_continuum = (
            ROOT / "openfoam/gate1b/rhoCentralFoamMUI/rhoCentralFoamMUI.C"
        ).read_text(encoding="utf-8")
        base_dsmc = (
            ROOT / "openfoam/gate3c/dsmcFoamGate3C/dsmcFoamGate3C.C"
        ).read_text(encoding="utf-8")
        self.assertIn("#define GATE3J_DISTRIBUTED", continuum)
        self.assertIn("#define GATE3J_DISTRIBUTED", dsmc)
        self.assertIn("unique_interface_ownership=true", base_continuum)
        self.assertIn("global_wall_flux_reduction=true", base_dsmc)
        self.assertIn("Foam::reduce", base_continuum)
        self.assertIn("Foam::reduce", base_dsmc)

    def test_gate3i_result_validator(self) -> None:
        result = ROOT / "docs/results/gate3i_unity_63786279.json"
        completed = subprocess.run(
            ["python3", str(ROOT / "scripts/require_gate3i_pass.py"), str(result)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
