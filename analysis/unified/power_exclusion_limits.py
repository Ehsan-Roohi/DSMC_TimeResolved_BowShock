#!/usr/bin/env python3
from __future__ import annotations
import argparse,math
from pathlib import Path
import numpy as np,pandas as pd
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
import correlated_noise_covariance_inference as cni
from campaign_utils import load_json

def interpolate_mode(theta_ref,mode_ref,theta):
 v=np.interp(theta,theta_ref,mode_ref); v=v/np.linalg.norm(v)
 if np.mean(v)<0: v=-v
 return v

def rank1_cov_for_global_std(mode,target):
 g=float(np.mean(mode))
 if abs(g)<1e-8: raise ValueError("Reference mode has near-zero angular mean.")
 return (target/g)**2*np.outer(mode,mode)

def detect(s,c,m):
 return bool(s.delta_aicc>10 and c.loocv_error_two_component<c.loocv_error_noise_only and m["uniform_mode_correlation"]>=0.65 and m["far_angle_mean_correlation"]>0 and c.projected_relative_correction_physical<0.20)

def crossing(amplitude,power,target):
 for i in range(1,len(power)):
  if power[i]>=target:
   if power[i]==power[i-1]: return float(amplitude[i])
   f=(target-power[i-1])/(power[i]-power[i-1]); return float(amplitude[i-1]+f*(amplitude[i]-amplitude[i-1]))
 return float("nan")

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--track",choices=["common200","full"],default="full"); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args(); cfg=load_json(a.config); optcfg=cfg["analysis"]["power_exclusion"]
 root=Path(cfg["paths"]["results_root"])/f"temporal_{a.track}"; corrroot=Path(cfg["paths"]["results_root"])/f"correlated_{a.track}"; out=Path(cfg["paths"]["results_root"])/f"power_{a.track}"; out.mkdir(parents=True,exist_ok=True)
 case_order=sorted(cfg["cases"],key=lambda x:x["kn"]); ref_label=optcfg.get("reference_case",case_order[0]["label"])
 refcentre,refwidth=cni.load_case_channels(root/ref_label,1); options=cni.FitOptions(phi_grid_size=int(optcfg["phi_grid"]),bootstrap_replicates=0,control_replicates=0,random_seed=int(optcfg["seed"]),far_angle_deg=float(cfg["analysis"]["correlated_noise"]["far_angle_deg"]))
 refs,_=cni.infer_scalar_model(refcentre,refwidth,options); refcov=cni.infer_covariance_fit(refcentre,refs,options); refmet=cni.covariance_metrics(refcentre.theta_deg,refcov.C_physical,refcov.C_noise,options.far_angle_deg); refmode=np.asarray(refmet["mode1"]); refsigma=float(refmet["global_physical_std_R"]); reftau=float(refs.tau_physical_exponential_star)
 multipliers=np.asarray(optcfg["amplitude_multipliers"],float); reps=int(optcfg["replicates"]); rows=[]; summaries=[]
 for ci,case in enumerate(case_order):
  centre,width=cni.load_case_channels(root/case["label"],1); s0,_=cni.infer_scalar_model(centre,width,options); cf0=cni.infer_covariance_fit(centre,s0,options); mode=interpolate_mode(refcentre.theta_deg,refmode,centre.theta_deg); phi_p=math.exp(-centre.dt_star/max(reftau,1e-12)); rng=np.random.default_rng(int(optcfg["seed"])+ci*10000)
  for mult in multipliers:
   amp=float(mult*refsigma); Cp=rank1_cov_for_global_std(mode,amp) if amp>0 else np.zeros_like(cf0.C_noise); hits=0
   for rep in range(reps):
    noise=cni.simulate_ar1(len(centre.arrays[1]),s0.phi_noise,cf0.C_noise,rng); phys=cni.simulate_ar1(len(centre.arrays[1]),phi_p,Cp,rng) if amp>0 else np.zeros_like(noise); wnoise=cni.simulate_ar1(len(centre.arrays[1]),s0.phi_noise,cf0.C_noise,rng)
    cs=cni.ChannelData(centre.theta_deg,centre.group_sizes,cni.construct_group_arrays(noise+phys,centre.group_sizes),centre.dt_star); ws=cni.ChannelData(centre.theta_deg,centre.group_sizes,cni.construct_group_arrays(wnoise,centre.group_sizes),centre.dt_star)
    sf,_=cni.infer_scalar_model(cs,ws,options); cv=cni.infer_covariance_fit(cs,sf,options); mm=cni.covariance_metrics(cs.theta_deg,cv.C_physical,cv.C_noise,options.far_angle_deg); hits+=int(detect(sf,cv,mm))
   power=hits/reps; rows.append({"case":case["label"],"Kn":case["kn"],"amplitude_multiplier":mult,"injected_global_std_R":amp,"detection_power":power,"replicates":reps})
  g=pd.DataFrame([r for r in rows if r["case"]==case["label"]]).sort_values("injected_global_std_R"); amps=g.injected_global_std_R.to_numpy(); pw=g.detection_power.to_numpy(); summaries.append({"case":case["label"],"Kn":case["kn"],"reference_global_std_R":refsigma,"false_detection_rate":float(pw[0]),"U90_global_std_R":crossing(amps,pw,.90),"U95_global_std_R":crossing(amps,pw,.95),"max_power":float(np.max(pw)),"n_raw_snapshots":len(centre.arrays[1])})
 pd.DataFrame(rows).to_csv(out/"power_curves.csv",index=False); S=pd.DataFrame(summaries).sort_values("Kn"); S.to_csv(out/"exclusion_limits.csv",index=False)
 fig,ax=plt.subplots(figsize=(8,5)); R=pd.DataFrame(rows)
 for case,g in R.groupby("case"):
  ax.plot(g.injected_global_std_R/refsigma,g.detection_power,marker="o",label=case)
 ax.axhline(.9,ls="--",lw=1); ax.set_xlabel("Injected global std / detected Kn=0.01 std"); ax.set_ylabel("Detection power"); ax.grid(True,alpha=.25); ax.legend(fontsize=7,ncol=2); fig.tight_layout(); fig.savefig(out/"Fig_power_curves_all_Kn.png",dpi=300); plt.close(fig)
 print(S.to_string(index=False))
if __name__=="__main__": main()
