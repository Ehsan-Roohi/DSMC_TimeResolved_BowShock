from __future__ import annotations
import importlib.util
import pathlib
import subprocess
import tempfile
import unittest

ROOT=pathlib.Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("analyze_gate3k",ROOT/"scripts/analyze_gate3k.py")
assert SPEC and SPEC.loader
ANALYZER=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(ANALYZER)

def segment(name: str,start: int,stop: int,session: str,changes: int,
            parcels: int,fluxes: list[tuple[int,float]]) -> str:
    windows=[]
    for index,flux in fluxes:
        windows += [
            f"GATE3G_WINDOW role=dsmc segment={name} window={index} step={(index+1)*200} samples=40 flux_checksum={flux} active_layer_changes={changes}",
            f"GATE3G_WINDOW role=continuum segment={name} window={index} step={(index+1)*200} feedback_scale=0.1 conservation_rel=1e-24",
        ]
    return "\n".join([
        f"MUI Rank 0 mpi://continuum/{session}",
        f"MUI Rank 2 mpi://dsmc/{session}",
        f"GATE3G_PASS role=continuum_live segment={name} start_step={start} stop_step={stop} steps={stop-start} first_step={start+1} last_step={stop} windows={(stop-start)//200} full_rhoCentralFoam_time_advance=true two_way_feedback_applied=true adaptive_sampling_surface=true adaptive_layer_changes={changes} min_feedback_scale=0.1 max_conservation_rel=1e-24 max_delta_U=1 max_delta_T=2",
        f"GATE3G_PASS role=dsmc_live segment={name} start_step={start} stop_step={stop} steps={stop-start} first_step={start+1} last_step={stop} windows={(stop-start)//200} final_parcels={parcels} inserted=100 active_layer_changes={changes} max_flux_checksum=5e-6 dynamic_activated_cells=1 deactivated_cells=0 seeded_parcels=66 removed_parcels=100 retained_identities=1000 inactive_parcels=0 ownership_balance_error=0 max_overlap_z=0.3 checkpoint_written=true",
        "GATE3J_PASS role=continuum_distributed spatial_ranks=2 unique_interface_ownership=true full_rhoCentralFoam_time_advance=true two_way_feedback_applied=true",
        f"GATE3J_PASS role=dsmc_distributed spatial_ranks=2 global_final_parcels={parcels} global_interface_ownership=true global_wall_flux_reduction=true full_dsmcFoam_time_advance=true",
        *windows,
    ])+"\n"

class Gate3KTest(unittest.TestCase):
    def test_analyzer_accepts_distributed_restart(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            continuous=root/"continuous.log"; fresh=root/"fresh.log"; restart=root/"restart.log"
            continuous.write_text(segment("continuous",0,400,"gate3k_continuous",60,8600,[(0,5e-6),(1,6e-6)]))
            fresh.write_text(segment("fresh",0,200,"gate3k_split",40,8500,[(0,5.1e-6)]))
            restart.write_text("GATE3G_STATE_LOADED step=200 layers=64 accumulators=64\n"+segment("restart",200,400,"gate3k_split",20,8550,[(1,6.2e-6)]))
            checkpoint=root/"checkpoint.state"
            checkpoint.write_text("GATE3G_STATE_V1 200 64\n"+"4 0\n"*64)
            result=ANALYZER.analyze(continuous,fresh,restart,checkpoint,str(root))
            self.assertEqual(result["status"],"PASS")
            self.assertTrue(result["restart_has_no_duplicated_or_missing_step"])

    def test_analyzer_rejects_missing_state_load(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)
            c=root/"c"; f=root/"f"; r=root/"r"; q=root/"q"
            c.write_text(segment("continuous",0,400,"gate3k_continuous",2,100,[(0,1),(1,1)]))
            f.write_text(segment("fresh",0,200,"gate3k_split",1,100,[(0,1)]))
            r.write_text(segment("restart",200,400,"gate3k_split",1,100,[(1,1)]))
            q.write_text("GATE3G_STATE_V1 200 64\n")
            with self.assertRaisesRegex(ValueError,"state was not restored"):
                ANALYZER.analyze(c,f,r,q,str(root))

    def test_runner_uses_real_distributed_restart(self):
        runner=(ROOT/"scripts/run_gate3k.sh").read_text()
        self.assertIn("run_pair continuous 0 400",runner)
        self.assertIn("run_pair fresh 0 200",runner)
        self.assertIn("run_pair restart 200 400",runner)
        self.assertIn("-parallel -world continuum",runner)
        self.assertIn("-parallel -world dsmc",runner)
        self.assertIn("checkpoint_200.state",runner)
        self.assertNotIn("-no-fields",runner)

    def test_gate3j_record_is_verified(self):
        result=subprocess.run(["python3",str(ROOT/"scripts/require_gate3j_pass.py"),
            str(ROOT/"docs/results/gate3j_unity_63797532.json")],
            text=True,capture_output=True,check=False)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=="__main__":
    unittest.main()
