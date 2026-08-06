#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import correlated_noise_covariance_inference as cni


def load_m1(case_dir: Path, smoothing: int=1):
    z=np.load(case_dir/f"marker_arrays_m1_ang{smoothing}.npz")
    return (
        np.asarray(z["theta_deg"],float),
        np.asarray(z["group_time_center_star"],float),
        np.asarray(z["s50_over_R"],float),
        np.asarray(z["delta_over_R"],float),
    )


def infer_window(theta,t,centre,width,start,stop,options,reference_mode):
    t=t[start:stop]; centre=centre[start:stop]; width=width[start:stop]
    dt=float(np.median(np.diff(t)))
    gs=[1,2,4,8,16]
    cs=cni.ChannelData(theta,gs,cni.construct_group_arrays(centre,gs),dt)
    ws=cni.ChannelData(theta,gs,cni.construct_group_arrays(width,gs),dt)
    sf,_=cni.infer_scalar_model(cs,ws,options)
    cv=cni.infer_covariance_fit(cs,sf,options)
    mm=cni.covariance_metrics(theta,cv.C_physical,cv.C_noise,options.far_angle_deg)
    mode=np.asarray(mm["mode1"],float)
    alignment=abs(float(np.dot(mode,reference_mode)))
    passed=bool(
        sf.delta_aicc>10
        and cv.loocv_error_two_component<cv.loocv_error_noise_only
        and alignment>=0.70
        and mm["far_angle_mean_correlation"]>0
        and cv.raw_negative_fraction_physical<0.20
    )
    return {
        "start":start,"stop":stop,"n":stop-start,
        "time_start_star":float(t[0]),"time_end_star":float(t[-1]),
        "delta_aicc":sf.delta_aicc,
        "loocv_ratio":cv.loocv_error_two_component/
                      max(cv.loocv_error_noise_only,1e-300),
        "phi_physical":sf.phi_physical,
        "tau_physical_star":sf.tau_physical_exponential_star,
        "mode_alignment_reference":alignment,
        "uniform_mode_correlation":mm["uniform_mode_correlation"],
        "far_angle_mean_correlation":mm["far_angle_mean_correlation"],
        "psd_correction_physical":
            cv.projected_relative_correction_physical,
        "strict_window_pass":int(passed),
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--reference-dir",required=True)
    ap.add_argument("--target-root",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--cases",nargs="+",
                    default=["Kn0p025","Kn0p050","Kn0p075","Kn0p10","Kn0p15"])
    ap.add_argument("--window",type=int,default=192)
    ap.add_argument("--step",type=int,default=48)
    ap.add_argument("--phi-grid",type=int,default=500)
    args=ap.parse_args()

    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    options=cni.FitOptions(
        phi_grid_size=args.phi_grid,
        bootstrap_replicates=0,
        control_replicates=0,
        psd_iterations=40,
        far_angle_deg=15.0,
    )
    rt,_,rc,_=load_m1(Path(args.reference_dir),1)
    # Reference mode from the complete reference marker record.
    gs=[1,2,4,8,16]
    rz=np.load(Path(args.reference_dir)/"marker_arrays_m1_ang1.npz")
    rw=np.asarray(rz["delta_over_R"],float)
    rtime=np.asarray(rz["group_time_center_star"],float)
    rdt=float(np.median(np.diff(rtime)))
    rcs=cni.ChannelData(rt,gs,cni.construct_group_arrays(rc,gs),rdt)
    rws=cni.ChannelData(rt,gs,cni.construct_group_arrays(rw,gs),rdt)
    rs,_=cni.infer_scalar_model(rcs,rws,options)
    rcv=cni.infer_covariance_fit(rcs,rs,options)
    rm=cni.covariance_metrics(rt,rcv.C_physical,rcv.C_noise,15.0)
    reference_mode=np.asarray(rm["mode1"],float)
    if np.mean(reference_mode)<0:
        reference_mode=-reference_mode

    rows=[]
    for case in args.cases:
        theta,t,centre,width=load_m1(Path(args.target_root)/case,1)
        ref=np.interp(theta,rt,reference_mode)
        ref=ref/np.linalg.norm(ref)
        n=len(t)
        for start in range(0,n-args.window+1,args.step):
            r=infer_window(
                theta,t,centre,width,start,start+args.window,options,ref
            )
            r.update({"case":case})
            rows.append(r)

    D=pd.DataFrame(rows)
    D.to_csv(out/"sliding_window_robustness.csv",index=False)

    cases=args.cases
    fig,axes=plt.subplots(len(cases),1,figsize=(10,2.2*len(cases)),
                          constrained_layout=True,sharex=False)
    if len(cases)==1:
        axes=[axes]
    for ax,case in zip(axes,cases):
        g=D[D.case==case]
        x=.5*(g.time_start_star+g.time_end_star)
        ax.plot(x,g.delta_aicc,marker="o",label=r"$\Delta AIC_c$")
        ax.axhline(10,ls="--",lw=1)
        passed=g.strict_window_pass.astype(bool).to_numpy()
        ax.scatter(x[passed],g.delta_aicc.to_numpy()[passed],
                   marker="*",s=120,label="strict pass")
        ax.set_ylabel(case)
        ax.grid(True,alpha=.25)
        ax.legend(fontsize=8)
    axes[-1].set_xlabel(r"window-centre time $t^*$")
    fig.suptitle("Sliding-window persistence of the collective displacement evidence")
    fig.savefig(out/"Fig_sliding_window_evidence.png",dpi=300,bbox_inches="tight")
    plt.close(fig)

    S=D.groupby("case").agg(
        n_windows=("strict_window_pass","size"),
        n_strict_pass=("strict_window_pass","sum"),
        strict_pass_fraction=("strict_window_pass","mean"),
        median_delta_aicc=("delta_aicc","median"),
        median_loocv_ratio=("loocv_ratio","median"),
        median_mode_alignment=("mode_alignment_reference","median"),
    ).reset_index()
    S.to_csv(out/"sliding_window_summary.csv",index=False)
    print(S.to_string(index=False))


if __name__=="__main__":
    main()
