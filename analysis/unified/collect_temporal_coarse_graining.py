#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from campaign_utils import load_json

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--track",choices=["common200","full"],required=True); a=ap.parse_args(); cfg=load_json(a.config)
 root=Path(cfg["paths"]["results_root"])/f"temporal_{a.track}"; out=Path(cfg["paths"]["results_root"])/"summary"/f"temporal_{a.track}"; out.mkdir(parents=True,exist_ok=True)
 kn={c["label"]:c["kn"] for c in cfg["cases"]}; ss=[]; ff=[]
 for d in root.iterdir():
  if not d.is_dir() or not (d/"coarse_graining_summary.csv").exists(): continue
  s=pd.read_csv(d/"coarse_graining_summary.csv"); s.insert(0,"case",d.name); s.insert(1,"Kn",kn.get(d.name,np.nan)); ss.append(s)
  f=pd.read_csv(d/"noise_floor_fits.csv"); f.insert(0,"case",d.name); f.insert(1,"Kn",kn.get(d.name,np.nan)); ff.append(f)
 if not ss: raise SystemExit("No temporal outputs")
 S=pd.concat(ss,ignore_index=True); F=pd.concat(ff,ignore_index=True); S.to_csv(out/"all_cases_coarse_graining_summary.csv",index=False); F.to_csv(out/"all_cases_noise_floor_fits.csv",index=False)
 p=S[(S.angular_smoothing_rays==1)&(S.quantity=="center")]
 fig,ax=plt.subplots(figsize=(8,5))
 for case,g in p.groupby("case"):
  g=g.sort_values("group_size"); ax.loglog(g.group_size,g.mean_point_std,marker="o",label=case)
 ax.set_xlabel("Temporal group size m"); ax.set_ylabel("Pointwise centre std"); ax.grid(True,which="both",alpha=.25); ax.legend(fontsize=7,ncol=2)
 fig.tight_layout(); fig.savefig(out/"Fig_center_coarse_graining_all_Kn.png",dpi=300); plt.close(fig)
if __name__=="__main__": main()
