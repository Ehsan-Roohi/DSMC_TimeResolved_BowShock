import tempfile,unittest
from pathlib import Path
from scripts.analyze_gate3n import analyze
class Gate3NTests(unittest.TestCase):
 def test_real_kn_gl_wiring(self):
  root=Path(__file__).resolve().parents[1];src=(root/"openfoam/gate1b/rhoCentralFoamMUI/rhoCentralFoamMUI.C").read_text();run=(root/"scripts/run_gate3n.sh").read_text()
  for token in ("updateKnGlField(knGl, rho, p, T, U)","hardSphereMeanFreePath","GATE3N_KNGL_WINDOW","readGate3nLayers"):self.assertIn(token,src)
  for token in ('cp "$GATE3M_RUN/gate3m.state" "$STATE"',"GATE3G_START_STEP=10000","GATE3G_STOP_STEP=12000"):self.assertIn(token,run)
  block=src[src.index("#ifdef GATE3N_KNGL\n            const int activeLayers"):];block=block[:block.index("#else")];self.assertIn("previousLayers[face]",block);self.assertNotIn("physicalLayersAtWindow",block)
 def test_analyzer(self):
  with tempfile.TemporaryDirectory() as td:
   x=Path(td);h=x/"h.csv";f=x/"KnGL";l=x/"log"
   h.write_text("window,step,face,theta_rad,previous_layers,requested_layers,current_layers,max_kn_gl\n"+"".join(f"{w},{w*200+1},{q},0,6,7,{7 if q==0 else 6},{.08 if q==0 else .01}\n" for w in range(50,60) for q in range(64)));f.write_text("FoamFile{}\n")
   l.write_text("GATE3G_PASS role=continuum_live steps=2000 windows=10\nGATE3G_PASS role=dsmc_live steps=2000 windows=10\nGATE3J_PASS role=continuum_distributed spatial_ranks=2\nGATE3J_PASS role=dsmc_distributed spatial_ranks=2\nGATE3N_PASS role=kn_gl_interface updates=10 windows=10 max_kn_gl=0.08 min_column_max_kn_gl=0.01 activate_threshold=0.05 deactivate_threshold=0.03 threshold_faces=1 layer_changes=10 live_field_written=true history_written=true\n")
   self.assertEqual(analyze(l,h,f,"run")["status"],"PASS")
if __name__=="__main__":unittest.main()
