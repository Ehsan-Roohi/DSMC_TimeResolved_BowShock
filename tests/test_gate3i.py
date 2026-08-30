from __future__ import annotations

import importlib.util
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
ANALYZER_PATH = ROOT / "scripts/analyze_gate3i.py"
SPEC = importlib.util.spec_from_file_location("analyze_gate3i", ANALYZER_PATH)
assert SPEC is not None and SPEC.loader is not None
ANALYZER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ANALYZER)


def rank_log(ranks: int) -> str:
    processor_dirs = 0 if ranks == 1 else ranks
    lines = [
        f"GATE3I_DECOMPOSITION role={role} ranks={ranks} "
        f"processor_dirs={processor_dirs} mesh_ok=true"
        for role in ("continuum", "dsmc")
    ]
    lines.extend(
        f"GATE3I_MUI_PASS role={role} local_rank={local_rank} "
        f"app_ranks={ranks} world_ranks={2*ranks} bidirectional=true"
        for role in ("continuum", "dsmc")
        for local_rank in range(ranks)
    )
    return "\n".join(lines) + "\n"


class Gate3ITest(unittest.TestCase):
    def test_analyzer_accepts_complete_preflight(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            logs = []
            for ranks in (1, 2, 4):
                path = root / f"gate3i_ranks_{ranks}.log"
                path.write_text(rank_log(ranks), encoding="utf-8")
                logs.append(path)
            summary = ANALYZER.analyze(logs, str(root))
            self.assertEqual(summary["status"], "PASS")
            self.assertTrue(summary["decomposed_openfoam_meshes_validated"])
            self.assertTrue(summary["multi_rank_bidirectional_mui_transport_completed"])
            self.assertFalse(summary["live_distributed_openfoam_dsmc_completed"])

    def test_analyzer_rejects_missing_rank(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            logs = []
            for ranks in (1, 2, 4):
                text = rank_log(ranks)
                if ranks == 4:
                    text = text.replace(
                        "GATE3I_MUI_PASS role=dsmc local_rank=3",
                        "GATE3I_MUI_SKIP role=dsmc local_rank=3",
                    )
                path = root / f"gate3i_ranks_{ranks}.log"
                path.write_text(text, encoding="utf-8")
                logs.append(path)
            with self.assertRaisesRegex(ValueError, "MUI inventory"):
                ANALYZER.analyze(logs, str(root))

    def test_runner_uses_real_openfoam_decomposition(self) -> None:
        runner = (ROOT / "scripts/run_gate3i.sh").read_text(encoding="utf-8")
        self.assertIn("decomposePar -case", runner)
        self.assertIn("-force -no-fields", runner)
        self.assertIn("-entry simpleCoeffs/n", runner)
        self.assertIn('-set "($ranks 1 1)"', runner)
        self.assertIn("checkMesh -parallel", runner)
        self.assertIn('-case "$case_dir" -constant', runner)
        self.assertIn("GATE3I_FAIL reason=decomposePar", runner)
        self.assertIn("for ranks in 1 2 4", runner)
        self.assertIn("mui_domain_decomposition_probe", runner)
        self.assertIn('BUILD_DIR=${BUILD_DIR:-"$ROOT/build/gate3i-$RUN_ID"}', runner)
        dictionary = (ROOT / "cases/gate3i/decomposeParDict").read_text(
            encoding="utf-8"
        )
        self.assertIn("method          simple;", dictionary)
        self.assertIn("n           (4 1 1);", dictionary)

    def test_builder_pins_mui_package_and_mpi_compiler(self) -> None:
        builder = (ROOT / "scripts/build_gate3i.sh").read_text(encoding="utf-8")
        self.assertIn('MUI_CONFIG="$MUI_PREFIX/MUI-2.0.0/share/MUI-2.0.0/cmake"', builder)
        self.assertIn('-DMUI_DIR="$MUI_CONFIG"', builder)
        self.assertIn('-DCMAKE_CXX_COMPILER="$(command -v mpic++)"', builder)
        self.assertIn('cmake --build "$MUI_BUILD" --target install', builder)

    def test_gate3h_result_validator(self) -> None:
        result = ROOT / "docs/results/gate3h_unity_63739461.json"
        completed = subprocess.run(
            ["python3", str(ROOT / "scripts/require_gate3h_pass.py"), str(result)],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
