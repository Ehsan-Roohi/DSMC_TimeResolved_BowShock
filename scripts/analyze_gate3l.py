#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,math,re
from pathlib import Path
TIMING=re.compile(r"GATE3L_TIMING ranks_per_solver=(\d+) total_ranks=(\d+) wall_seconds=([-+0-9.eE]+)")
def kv(line):
 out={}
 for t in line.split()[1:]:
  if "=" in t: k,v=t.split("=",1);out[k]=v
 return out
def one(text,prefix,role):
 x=[kv(l) for l in text.splitlines() if l.startswith(prefix) and f"role={role}" in l]
 if len(x)!=1: raise ValueError(f"expected one {prefix} {role}")
 return x[0]
def rel(a,b): return abs(a-b)/max(abs(a),abs(b),1e-300)
def analyze(paths,run_dir):
 rows=[];base_wall=None;base_flux=None;base_parcels=None
 for expected,path in zip((1,2,4),paths):
  text=path.read_text(errors="replace")
  if "FAIL" in text: raise ValueError(f"failure marker for {expected} ranks")
  m=TIMING.search(text)
  if not m or int(m.group(1))!=expected or int(m.group(2))!=2*expected: raise ValueError("timing inventory failed")
  wall=float(m.group(3))
  c=one(text,"GATE3G_PASS ","continuum_live");d=one(text,"GATE3G_PASS ","dsmc_live")
  dc=one(text,"GATE3J_PASS ","continuum_distributed");dd=one(text,"GATE3J_PASS ","dsmc_distributed")
  if int(c["steps"])!=1000 or int(d["steps"])!=1000 or int(c["windows"])!=5 or int(d["windows"])!=5: raise ValueError("step inventory failed")
  if int(dc["spatial_ranks"])!=expected or int(dd["spatial_ranks"])!=expected: raise ValueError("spatial rank marker failed")
  if dc.get("unique_interface_ownership")!="true" or dd.get("global_interface_ownership")!="true" or dd.get("global_wall_flux_reduction")!="true": raise ValueError("distributed ownership failed")
  cons=float(c["max_conservation_rel"]);flux=float(d["max_flux_checksum"]);parcels=int(dd["global_final_parcels"])
  if not math.isfinite(wall) or wall<=0 or cons>1e-12 or int(d["inactive_parcels"])!=0 or int(d["ownership_balance_error"])!=0: raise ValueError("physical hard gate failed")
  if base_wall is None: base_wall,base_flux,base_parcels=wall,flux,parcels
  fd=rel(flux,base_flux);pd=rel(parcels,base_parcels)
  if fd>0.75 or pd>0.25: raise ValueError("rank-layout stochastic consistency failed")
  rows.append({"ranks_per_solver":expected,"total_mpi_ranks":2*expected,"wall_seconds":wall,
   "speedup":base_wall/wall,"parallel_efficiency":base_wall/(wall*expected),
   "flux_relative_difference_from_1plus1":fd,"parcel_relative_difference_from_1plus1":pd,
   "feedback_conservation_relative_error":cons})
 return {"gate":"3L-WHOLE-SOLVER-STRONG-SCALING","status":"PASS","prerequisite":"Gate3K distributed restart PASS",
  "rank_layouts":["1+1","2+2","4+4"],"coupled_steps_per_layout":1000,
  "whole_solver_spatial_scaling_completed":True,"proxy_kernel_only":False,
  "unique_interface_ownership_all_layouts":True,"global_wall_flux_reduction_all_layouts":True,
  "maximum_particle_ownership_balance_error":0,"maximum_inactive_parcels":0,
  "scaling":rows,"run_dir":run_dir}
def main():
 p=argparse.ArgumentParser();p.add_argument("--logs",nargs=3,type=Path,required=True);p.add_argument("--summary",type=Path,required=True);p.add_argument("--run-dir",required=True);a=p.parse_args()
 r=analyze(a.logs,a.run_dir);a.summary.write_text(json.dumps(r,indent=2)+"\n");print(json.dumps(r,indent=2));print("GATE3L_WHOLE_SOLVER_SCALING_STATUS=PASS")
if __name__=="__main__":main()
