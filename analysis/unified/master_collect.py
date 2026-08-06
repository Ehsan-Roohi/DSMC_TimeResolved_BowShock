#!/usr/bin/env python3
from __future__ import annotations
import argparse,io
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
from campaign_utils import load_json

def classify(r):
 resolved=(r.get("bootstrap_delta_aicc_q025",-np.inf)>0 and r.get("loocv_error_two_component",np.inf)<r.get("loocv_error_noise_only",-np.inf) and r.get("negative_control_false_detection_rate",1)<=.10 and r.get("positive_control_detection_rate",0)>=.90 and r.get("bootstrap_far_angle_mean_correlation_q025",-np.inf)>0 and r.get("bootstrap_uniform_mode_correlation_q025",0)>=.65 and r.get("projected_relative_correction_physical",1)<.15)
 if resolved: return "Resolved collective mode"
 if np.isfinite(r.get("U90_global_std_R",np.nan)) and r.get("U90_global_std_R",np.inf)<r.get("reference_global_std_R",-np.inf): return "Not detected with adequate sensitivity"
 if r.get("delta_aicc",-np.inf)>10 and r.get("uniform_mode_correlation",0)>.65: return "Transitional / ambiguous"
 return "Unmeasurable at current sample size"

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--track",choices=["common200","full"],default="common200"); a=ap.parse_args(); cfg=load_json(a.config); rr=Path(cfg["paths"]["results_root"]); out=rr/"summary"/f"master_{a.track}"; out.mkdir(parents=True,exist_ok=True)
 cases=pd.DataFrame(cfg["cases"])[["label","kn","available_snapshots","dt_star"]].rename(columns={"label":"case","kn":"Kn"})
 q=pd.read_csv(rr/"qc"/"preflight_qc.csv"); pod=pd.read_csv(rr/"summary"/"pod"/"corrected_pod_summary.csv"); inf=pd.read_csv(rr/f"correlated_{a.track}"/"correlated_noise_inference_summary.csv"); inf=inf[inf.angular_smoothing_rays==1].copy(); power_path=rr/f"power_{a.track}"/"exclusion_limits.csv"; power=pd.read_csv(power_path) if power_path.exists() else pd.DataFrame(columns=["case"])
 pwide=pod[pod.run.str.startswith("common200_")].copy(); pwide["variable"]=pwide.run.str.replace("common200_","",regex=False); pwide=pwide.pivot(index="case",columns="variable",values="E1").add_prefix("POD_E1_").reset_index(); geom=pod[pod.run.eq("common200_multivariate")][["case","delta_over_R","s_marker_over_R","physical_window_valid_fraction"]]
 M=cases.merge(q.drop(columns=["Kn"],errors="ignore"),on="case",how="left").merge(geom,on="case",how="left").merge(pwide,on="case",how="left").merge(inf.drop(columns=["Kn"],errors="ignore"),on="case",how="left").merge(power.drop(columns=["Kn"],errors="ignore"),on="case",how="left")
 M["classification"]=M.apply(classify,axis=1); M=M.sort_values("Kn"); M.to_csv(out/"master_results.csv",index=False)
 fig,axes=plt.subplots(2,2,figsize=(11,8),constrained_layout=True)
 axes[0,0].semilogx(M.Kn,M.delta_aicc,marker="o"); axes[0,0].axhline(10,ls="--",lw=1); axes[0,0].set_ylabel(r"$\Delta AIC_c$")
 axes[0,1].semilogx(M.Kn,M.uniform_mode_correlation,marker="o"); axes[0,1].set_ylabel("Uniform-mode correlation")
 axes[1,0].semilogx(M.Kn,M.far_angle_mean_correlation,marker="o"); axes[1,0].axhline(0,lw=1); axes[1,0].set_ylabel("Far-angle correlation")
 axes[1,1].semilogx(M.Kn,M.tau_physical_exponential_star,marker="o"); axes[1,1].set_ylabel(r"$\tau_p^*$")
 for ax in axes.ravel(): ax.set_xlabel("Kn"); ax.grid(True,alpha=.25)
 fig.suptitle("Noise-separated collective-displacement diagnostics across all Kn"); fig.savefig(out/"Fig_master_collectivity_vs_Kn.png",dpi=300,bbox_inches="tight"); plt.close(fig)
 if "U90_global_std_R" in M:
  fig,ax=plt.subplots(figsize=(8,5)); ax.semilogx(M.Kn,M.global_physical_std_R,marker="o",label="Inferred physical std"); ax.semilogx(M.Kn,M.U90_global_std_R,marker="s",label="90% exclusion/detection limit"); ax.set_xlabel("Kn"); ax.set_ylabel(r"Global displacement std $s/R$"); ax.grid(True,alpha=.25); ax.legend(); fig.tight_layout(); fig.savefig(out/"Fig_master_amplitude_and_exclusion_limit.png",dpi=300); plt.close(fig)
 # covariance heatmaps
 valid=[]
 for _,r in M.iterrows():
  p=rr/f"correlated_{a.track}"/r["case"]/"ang1"/"inferred_covariances.npz"
  if p.exists(): valid.append((r["case"],r["Kn"],p))
 if valid:
  fig,axes=plt.subplots(1,len(valid),figsize=(3.2*len(valid),3.4),squeeze=False,constrained_layout=True)
  for ax,(case,kn,p) in zip(axes.ravel(),valid):
   z=np.load(p); C=z["C_physical"]; d=np.sqrt(np.maximum(np.diag(C),0)); R=C/np.maximum(d[:,None]*d[None,:],1e-300); th=z["theta_deg"]; im=ax.imshow(np.clip(R,-1,1),origin="lower",extent=[th[0],th[-1],th[0],th[-1]],vmin=-1,vmax=1,cmap="coolwarm",aspect="equal"); ax.set_title(case); ax.set_xlabel(r"$\theta'$ [deg]")
  axes[0,0].set_ylabel(r"$\theta$ [deg]"); fig.colorbar(im,ax=axes.ravel().tolist(),shrink=.8,label="Physical correlation"); fig.savefig(out/"Fig_master_physical_correlation_matrices.png",dpi=300,bbox_inches="tight"); plt.close(fig)
 print(M[["case","Kn","classification"]].to_string(index=False))
if __name__=="__main__": main()
