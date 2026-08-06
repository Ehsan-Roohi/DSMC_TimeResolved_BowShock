#!/usr/bin/env python3
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from campaign_utils import load_json

def qcdict(path):
    q=pd.read_csv(path); return dict(zip(q["quantity"].astype(str),q["value"].astype(str)))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); a=ap.parse_args(); cfg=load_json(a.config)
    root=Path(cfg["paths"]["results_root"])/"corrected_pod"; out=Path(cfg["paths"]["results_root"])/"summary"/"pod"; out.mkdir(parents=True,exist_ok=True)
    knmap={c["label"]:float(c["kn"]) for c in cfg["cases"]}; rows=[]
    for case in sorted((p for p in root.iterdir() if p.is_dir()),key=lambda p:knmap.get(p.name,999)):
      for run in sorted(p for p in case.iterdir() if p.is_dir()):
       try:
        pod=pd.read_csv(run/"pod_energy.csv"); dmd=pd.read_csv(run/"dmd_eigs.csv"); qc=qcdict(run/"shock_window_qc_summary.csv")
       except Exception as e: print("SKIP",run,e); continue
       E=pod.energy_fraction.to_numpy(float); C=pod.cumulative_energy.to_numpy(float)
       rows.append({"case":case.name,"Kn":knmap.get(case.name,np.nan),"run":run.name,
        "n_snapshots":int(float(qc.get("n_snapshots",0))),"physical_window_valid_fraction":float(qc.get("physical_window_valid_fraction",np.nan)),
        "s_marker_over_R":float(qc.get("median_s_peak_over_R",np.nan)),"delta_over_R":float(qc.get("median_delta_rho_over_R",np.nan)),
        "E1":E[0],"C10":C[min(9,len(C)-1)],"N90":int(np.searchsorted(C,.90)+1),"N95":int(np.searchsorted(C,.95)+1),
        "dmd_max_abs_lambda":float(dmd.abs_lambda.max()),"dmd_max_growth":float(dmd.omega_real_growth.max())})
    df=pd.DataFrame(rows); df.to_csv(out/"corrected_pod_summary.csv",index=False)
    common=df[df.run.str.startswith("common200_",na=False)].copy(); common["variable"]=common.run.str.replace("common200_","",regex=False)
    order=["D","MA","TTR","TRT","P","multivariate"]; cases=[c["label"] for c in sorted(cfg["cases"],key=lambda x:x["kn"])]
    mat=common.pivot(index="variable",columns="case",values="E1").reindex(index=order,columns=cases)
    mat.to_csv(out/"common200_E1.csv")
    fig,ax=plt.subplots(figsize=(10,4.8)); im=ax.imshow(100*mat.values,aspect="auto",vmin=0)
    ax.set_xticks(range(len(cases)),cases,rotation=35,ha="right"); ax.set_yticks(range(len(order)),order)
    for i in range(mat.shape[0]):
      for j in range(mat.shape[1]):
       if np.isfinite(mat.iloc[i,j]): ax.text(j,i,f"{100*mat.iloc[i,j]:.1f}",ha="center",va="center",fontsize=8)
    fig.colorbar(im,ax=ax,label="POD mode-1 energy [%]"); ax.set_title("Corrected physical-domain POD across all Kn")
    fig.tight_layout(); fig.savefig(out/"Fig_corrected_POD_E1_all_Kn.png",dpi=300); plt.close(fig)
if __name__=="__main__": main()
