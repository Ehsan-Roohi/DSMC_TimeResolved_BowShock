import pathlib,subprocess,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class Gate3MTest(unittest.TestCase):
 def test_long_real_solver_runner(self):
  s=(ROOT/"scripts/run_gate3m.sh").read_text()
  self.assertIn("GATE3G_STOP_STEP=10000",s);self.assertIn("windows=50",s)
  self.assertIn("-np 2 env",s);self.assertIn("-parallel -world continuum",s);self.assertIn("-parallel -world dsmc",s)
  self.assertIn("rhoCentralFoamGate3J",s);self.assertIn("dsmcFoamGate3J",s)
 def test_gate3l_record(self):
  r=subprocess.run(["python3",str(ROOT/"scripts/require_gate3l_pass.py"),str(ROOT/"docs/results/gate3l_unity_63806295.json")],capture_output=True,text=True)
  self.assertEqual(r.returncode,0,r.stderr)
 def test_long_segment_has_bounded_solver_support(self):
  for path in (ROOT/"openfoam/gate1b/rhoCentralFoamMUI/rhoCentralFoamMUI.C",ROOT/"openfoam/gate3c/dsmcFoamGate3C/dsmcFoamGate3C.C"):
   source=path.read_text()
   self.assertIn("gate3gMaximumSegmentStep = 10000",source)
   self.assertIn("parsed > gate3gMaximumSegmentStep",source)
   self.assertNotIn("parsed > 1000",source)
if __name__=="__main__":unittest.main()
