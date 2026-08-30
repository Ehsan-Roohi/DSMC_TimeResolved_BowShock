import pathlib,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Gate3LTest(unittest.TestCase):
 def test_runner_is_whole_solver_scaling(self):
  s=(ROOT/"scripts/run_gate3l.sh").read_text()
  self.assertIn("for ranks in 1 2 4",s);self.assertIn("GATE3G_STOP_STEP=1000",s)
  self.assertIn("rhoCentralFoamGate3J",s);self.assertIn("dsmcFoamGate3J",s)
  self.assertIn('"${par[@]}" -world continuum',s)
  self.assertIn('"${par[@]}" -world dsmc',s)
  self.assertIn("OMPI_MCA_pml",s)
  self.assertNotIn("dynamic_restart_scaling",s)
 def test_gate3k_record(self):
  r=subprocess.run(["python3",str(ROOT/"scripts/require_gate3k_pass.py"),str(ROOT/"docs/results/gate3k_unity_63804488.json")],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
if __name__=="__main__":unittest.main()
