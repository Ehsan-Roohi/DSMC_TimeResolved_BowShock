#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys,shlex
from pathlib import Path
from campaign_utils import load_json

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--track",choices=["common200","full"],required=True); ap.add_argument("--dry-run",action="store_true"); a=ap.parse_args(); cfg=load_json(a.config); o=cfg["analysis"]["correlated_noise"]; here=Path(__file__).resolve().parent
 root=Path(cfg["paths"]["results_root"])/f"temporal_{a.track}"; out=Path(cfg["paths"]["results_root"])/f"correlated_{a.track}"
 cmd=[sys.executable,str(here/"correlated_noise_covariance_inference.py"),"--root",str(root),"--out",str(out),"--angular-smoothing","1","3","5","--bootstrap",str(o["bootstrap"]),"--controls",str(o["controls"]),"--phi-grid",str(o["phi_grid"]),"--max-acf-lag",str(o["max_acf_lag"]),"--far-angle-deg",str(o["far_angle_deg"]),"--seed",str(o["seed"])]
 print(">>>"," ".join(shlex.quote(str(x)) for x in cmd))
 if not a.dry_run: out.mkdir(parents=True,exist_ok=True); subprocess.run(cmd,check=True)
if __name__=="__main__": main()
