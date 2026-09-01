#!/usr/bin/env python3
import argparse,csv,json,math
from pathlib import Path
def kv(line):
 out={}
 for t in line.split()[1:]:
  if "=" in t:k,v=t.split("=",1);out[k]=v
 return out
def one(text,prefix,role):
 rows=[kv(x) for x in text.splitlines() if x.startswith(prefix) and f"role={role}" in x]
 if len(rows)!=1:raise ValueError(f"expected one {prefix}{role}, got {len(rows)}")
 return rows[0]
def analyze(log,history,field,run_dir):
 text=log.read_text(errors="replace")
 if "GATE3N_FAIL" in text:raise ValueError("Gate3N failure marker")
 kn=one(text,"GATE3N_PASS ","kn_gl_interface");c=one(text,"GATE3G_PASS ","continuum_live");d=one(text,"GATE3G_PASS ","dsmc_live");dc=one(text,"GATE3J_PASS ","continuum_distributed");dd=one(text,"GATE3J_PASS ","dsmc_distributed")
 if int(kn["updates"])!=10 or int(kn["windows"])!=10:raise ValueError("wrong Kn_GL update inventory")
 if float(kn["activate_threshold"])!=.05 or float(kn["deactivate_threshold"])!=.03:raise ValueError("wrong thresholds")
 if float(kn["max_kn_gl"])<.05 or int(kn["threshold_faces"])<=0 or int(kn["layer_changes"])<=0:raise ValueError("Kn_GL did not drive interface")
 if int(c["steps"])!=2000 or int(d["steps"])!=2000 or int(c["windows"])!=10 or int(d["windows"])!=10:raise ValueError("solver inventory")
 if int(dc["spatial_ranks"])!=2 or int(dd["spatial_ranks"])!=2:raise ValueError("layout")
 if not history.is_file() or not field.is_file() or field.stat().st_size==0:raise ValueError("missing diagnostics")
 with history.open() as stream:rows=list(csv.DictReader(stream))
 windows={int(r["window"]) for r in rows};faces={int(r["face"]) for r in rows}
 if len(rows)!=640 or windows!=set(range(50,60)) or faces!=set(range(64)):raise ValueError("history inventory")
 layers=[int(r["current_layers"]) for r in rows];values=[float(r["max_kn_gl"]) for r in rows]
 if not all(4<=x<=12 for x in layers) or not all(math.isfinite(x) and x>=0 for x in values):raise ValueError("invalid history")
 return {"gate":"3N-KNGL-LIVE-ADAPTIVE-INTERFACE","status":"PASS","prerequisite":"Gate3M PASS","criterion":"max(Kn_GL_rho, Kn_GL_T, Kn_GL_U)","mean_free_path_model":"hard-sphere argon, diameter 4.17e-10 m","activation_threshold":.05,"deactivation_threshold":.03,"restart_step":10000,"stop_step":12000,"coupled_steps":2000,"coupling_windows":10,"selected_rank_layout":"2+2","maximum_kn_gl":float(kn["max_kn_gl"]),"adaptive_layer_changes":int(kn["layer_changes"]),"minimum_active_layers":min(layers),"maximum_active_layers":max(layers),"kn_gl_field":str(field),"kn_gl_history":str(history),"run_dir":run_dir,"live_log":str(log)}
def main():
 p=argparse.ArgumentParser();p.add_argument("--live",type=Path,required=True);p.add_argument("--history",type=Path,required=True);p.add_argument("--field",type=Path,required=True);p.add_argument("--summary",type=Path,required=True);p.add_argument("--run-dir",required=True);a=p.parse_args();r=analyze(a.live,a.history,a.field,a.run_dir);a.summary.write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r,indent=2));print("GATE3N_KNGL_STATUS=PASS")
if __name__=="__main__":main()
