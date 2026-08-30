#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math
from pathlib import Path
def kv(line):
 out={}
 for token in line.split()[1:]:
  if "=" in token:
   k,v=token.split("=",1);out[k]=v
 return out
def one(text,prefix,role):
 rows=[kv(x) for x in text.splitlines() if x.startswith(prefix) and f"role={role}" in x]
 if len(rows)!=1: raise ValueError(f"expected one {prefix}{role}, got {len(rows)}")
 return rows[0]
def true(row,key):
 if row.get(key)!="true": raise ValueError(f"{key} is not true")
def analyze(log:Path,run_dir:str):
 text=log.read_text(errors="replace")
 if "FAIL" in text: raise ValueError("failure marker in long-run log")
 c=one(text,"GATE3G_PASS ","continuum_live");d=one(text,"GATE3G_PASS ","dsmc_live")
 dc=one(text,"GATE3J_PASS ","continuum_distributed");dd=one(text,"GATE3J_PASS ","dsmc_distributed")
 for row in (c,d):
  if int(row["steps"])!=10000 or int(row["first_step"])!=1 or int(row["last_step"])!=10000 or int(row["windows"])!=50:
   raise ValueError("long-run step/window inventory failed")
 if int(dc["spatial_ranks"])!=2 or int(dd["spatial_ranks"])!=2: raise ValueError("2+2 rank inventory failed")
 for row,key in ((c,"full_rhoCentralFoam_time_advance"),(c,"two_way_feedback_applied"),(dc,"unique_interface_ownership"),(dd,"global_interface_ownership"),(dd,"global_wall_flux_reduction"),(dd,"full_dsmcFoam_time_advance"),(d,"checkpoint_written")): true(row,key)
 cons=float(c["max_conservation_rel"]);flux=float(d["max_flux_checksum"]);scale=float(c["min_feedback_scale"])
 parcels=int(dd["global_final_parcels"]);ownership=int(d["ownership_balance_error"]);inactive=int(d["inactive_parcels"])
 values=(cons,flux,scale,float(c["max_delta_U"]),float(c["max_delta_T"]))
 if not all(math.isfinite(x) for x in values): raise ValueError("non-finite long-run metric")
 if cons>1e-12 or flux<=0 or scale<=0 or parcels<=0 or parcels>10000000 or ownership!=0 or inactive!=0: raise ValueError("long-run physical hard gate failed")
 if int(c["adaptive_layer_changes"])<=0 or int(d["active_layer_changes"])<=0 or int(d["retained_identities"])<=0: raise ValueError("adaptive-domain persistence failed")
 return {"gate":"3M-LONG-MULTIWINDOW-STABILITY","status":"PASS","prerequisite":"Gate3L whole-solver scaling PASS",
  "selected_rank_layout":"2+2","coupled_steps":10000,"coupling_windows":50,
  "full_rhoCentralFoam_time_advance":True,"full_dsmcFoam_time_advance":True,
  "physical_two_way_feedback_applied":True,"adaptive_particle_domain_persisted":True,
  "unique_interface_ownership":True,"global_wall_flux_reduction":True,
  "maximum_feedback_conservation_relative_error":cons,"maximum_particle_ownership_balance_error":ownership,
  "maximum_inactive_parcels":inactive,"global_final_parcels":parcels,"maximum_flux_checksum":flux,
  "minimum_feedback_scale":scale,"checkpoint_written":True,"run_dir":run_dir,"live_log":str(log)}
def main():
 p=argparse.ArgumentParser();p.add_argument("--live",type=Path,required=True);p.add_argument("--summary",type=Path,required=True);p.add_argument("--run-dir",required=True);a=p.parse_args()
 result=analyze(a.live,a.run_dir);a.summary.write_text(json.dumps(result,indent=2)+"\n");print(json.dumps(result,indent=2));print("GATE3M_LONG_STABILITY_STATUS=PASS")
if __name__=="__main__":main()
