#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys,shlex
from pathlib import Path
from campaign_utils import load_json

def complete(out): return all((out/x).exists() for x in ["coarse_graining_summary.csv","noise_floor_fits.csv","coarse_graining_metadata.json"])
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--track",choices=["common200","full"],required=True); ap.add_argument("--dry-run",action="store_true")
 a=ap.parse_args(); cfg=load_json(a.config); tcg=cfg["analysis"]["temporal_coarse_graining"]; here=Path(__file__).resolve().parent
 outroot=Path(cfg["paths"]["results_root"])/f"temporal_{a.track}"; outroot.mkdir(parents=True,exist_ok=True)
 for case in cfg["cases"]:
  count=int(cfg["analysis"]["common_n"]) if a.track=="common200" else int(case.get("full_count",0))
  out=outroot/case["label"]
  cmd=[sys.executable,str(here/"analyze_temporal_coarse_graining.py"),"--pattern",case["pattern"],"--out",str(out),"--dt-star",str(case["dt_star"]),"--count",str(count),
   "--start-index",str(case.get("common_start_index",0)),"--theta-min",str(tcg["theta_min"]),"--theta-max",str(tcg["theta_max"]),"--ntheta",str(tcg["ntheta"]),
   "--nr-raw",str(tcg["nr_raw"]),"--smax-R",str(tcg["smax_R"]),"--wall-exclude-R",str(tcg["wall_exclude_R"]),"--smooth-sigma",str(tcg["smooth_sigma"]),
   "--group-sizes",*[str(x) for x in tcg["group_sizes"]],"--theta-smooth-rays",*[str(x) for x in tcg["theta_smooth_rays"]]]
  print("\n>>>"," ".join(shlex.quote(str(x)) for x in cmd))
  if complete(out): print("SKIP completed",out)
  elif not a.dry_run: subprocess.run(cmd,check=True)
if __name__=="__main__": main()
