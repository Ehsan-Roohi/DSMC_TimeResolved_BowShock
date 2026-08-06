#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

import correlated_noise_covariance_inference as cni


def wilson_interval(hits: int, n: int, z: float = 1.959963984540054):
    if n <= 0:
        return np.nan, np.nan
    p = hits / n
    den = 1.0 + z*z/n
    center = (p + z*z/(2*n))/den
    half = z*math.sqrt(p*(1-p)/n + z*z/(4*n*n))/den
    return max(0.0, center-half), min(1.0, center+half)


def interpolate_mode(theta_ref, mode_ref, theta):
    v = np.interp(theta, theta_ref, mode_ref)
    v = v / np.linalg.norm(v)
    if np.mean(v) < 0:
        v = -v
    return v


def rank1_cov_for_global_std(mode, target):
    g = float(np.mean(mode))
    if abs(g) < 1e-12:
        raise ValueError("Reference mode has near-zero angular mean.")
    return (target/g)**2 * np.outer(mode, mode)


def crossing(x, y, target):
    x=np.asarray(x,float); y=np.asarray(y,float)
    order=np.argsort(x); x=x[order]; y=y[order]
    y=np.maximum.accumulate(y)
    for i in range(1,len(y)):
        if y[i] >= target:
            if y[i] == y[i-1]:
                return float(x[i])
            f=(target-y[i-1])/(y[i]-y[i-1])
            return float(x[i-1]+f*(x[i]-x[i-1]))
    return np.nan


def detect_reference(sf, cv, mm, injected_mode):
    recovered=np.asarray(mm["mode1"],float)
    alignment=abs(float(np.dot(recovered,injected_mode)))
    return bool(
        sf.delta_aicc > 10.0
        and cv.loocv_error_two_component < cv.loocv_error_noise_only
        and alignment >= 0.70
        and mm["far_angle_mean_correlation"] > 0.0
        and cv.raw_negative_fraction_physical < 0.20
    ), alignment


def detect_uniform(sf, cv, mm):
    return bool(
        sf.delta_aicc > 10.0
        and cv.loocv_error_two_component < cv.loocv_error_noise_only
        and mm["uniform_mode_correlation"] >= 0.65
        and mm["far_angle_mean_correlation"] > 0.0
        and cv.raw_negative_fraction_physical < 0.20
    )


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--reference-dir",required=True)
    ap.add_argument("--target-root",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--cases",nargs="+",
                    default=["Kn0p025","Kn0p050","Kn0p075","Kn0p10","Kn0p15"])
    ap.add_argument("--replicates",type=int,default=100)
    ap.add_argument("--phi-grid",type=int,default=220)
    ap.add_argument("--seed",type=int,default=40231)
    ap.add_argument("--far-angle-deg",type=float,default=15.0)
    ap.add_argument("--amplitude-multipliers",nargs="+",type=float,
                    default=[0,0.25,0.5,0.75,1.0,1.25,1.5,2,3,4,6])
    args=ap.parse_args()

    reference_dir=Path(args.reference_dir)
    target_root=Path(args.target_root)
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    detail_file=out/"final_power_replicates.csv"

    options=cni.FitOptions(
        phi_grid_size=args.phi_grid,
        bootstrap_replicates=0,
        control_replicates=0,
        psd_iterations=0,
        random_seed=args.seed,
        far_angle_deg=args.far_angle_deg,
    )

    refcentre,refwidth=cni.load_case_channels(reference_dir,1)
    refs,_=cni.infer_scalar_model(refcentre,refwidth,options)
    refcov=cni.infer_covariance_fit(refcentre,refs,options)
    refmet=cni.covariance_metrics(
        refcentre.theta_deg,refcov.C_physical,refcov.C_noise,args.far_angle_deg
    )
    refmode=np.asarray(refmet["mode1"],float)
    if np.mean(refmode)<0:
        refmode=-refmode
    refsigma=float(refmet["global_physical_std_R"])
    reftau=float(refs.tau_physical_exponential_star)

    existing=pd.DataFrame()
    if detail_file.exists():
        existing=pd.read_csv(detail_file)

    rows=[] if existing.empty else existing.to_dict("records")

    for ci,case in enumerate(args.cases):
        print(f"\nPREPARE {case}",flush=True)
        centre,width=cni.load_case_channels(target_root/case,1)
        s0,_=cni.infer_scalar_model(centre,width,options)
        cf0=cni.infer_covariance_fit(centre,s0,options)
        injected_mode=interpolate_mode(refcentre.theta_deg,refmode,centre.theta_deg)
        phi_p=math.exp(-centre.dt_star/max(reftau,1e-12))

        for mult in args.amplitude_multipliers:
            done=0
            if not existing.empty:
                done=int(((existing.case==case)&
                          np.isclose(existing.amplitude_multiplier,float(mult))).sum())
            if done>=args.replicates:
                print(f"SKIP {case} multiplier={mult}: {done} replicates exist",flush=True)
                continue

            rng=np.random.default_rng(
                args.seed + ci*100000 + int(round(float(mult)*1000))*100 + done
            )
            amp=float(mult*refsigma)
            Cp=(rank1_cov_for_global_std(injected_mode,amp)
                if amp>0 else np.zeros_like(cf0.C_noise))
            print(f"RUN {case} multiplier={mult:g}; remaining={args.replicates-done}",
                  flush=True)

            for rep in range(done,args.replicates):
                n=len(centre.arrays[1])
                noise=cni.simulate_ar1(n,s0.phi_noise,cf0.C_noise,rng)
                physical=(cni.simulate_ar1(n,phi_p,Cp,rng)
                          if amp>0 else np.zeros_like(noise))
                width_noise=cni.simulate_ar1(n,s0.phi_noise,cf0.C_noise,rng)

                cs=cni.ChannelData(
                    centre.theta_deg,centre.group_sizes,
                    cni.construct_group_arrays(noise+physical,centre.group_sizes),
                    centre.dt_star
                )
                ws=cni.ChannelData(
                    centre.theta_deg,centre.group_sizes,
                    cni.construct_group_arrays(width_noise,centre.group_sizes),
                    centre.dt_star
                )
                sf,_=cni.infer_scalar_model(cs,ws,options)
                cv=cni.infer_covariance_fit(cs,sf,options)
                mm=cni.covariance_metrics(
                    cs.theta_deg,cv.C_physical,cv.C_noise,args.far_angle_deg
                )
                hit_ref,align=detect_reference(sf,cv,mm,injected_mode)
                hit_uniform=detect_uniform(sf,cv,mm)

                rows.append({
                    "case":case,
                    "amplitude_multiplier":float(mult),
                    "replicate":rep+1,
                    "injected_global_std_R":amp,
                    "reference_global_std_R":refsigma,
                    "reference_tau_star":reftau,
                    "detected_reference_criterion":int(hit_ref),
                    "detected_uniform_criterion":int(hit_uniform),
                    "delta_aicc":sf.delta_aicc,
                    "loocv_ratio":cv.loocv_error_two_component/
                                  max(cv.loocv_error_noise_only,1e-300),
                    "mode_alignment_reference":align,
                    "uniform_mode_correlation":mm["uniform_mode_correlation"],
                    "far_angle_mean_correlation":mm["far_angle_mean_correlation"],
                    "raw_negative_fraction_physical":
                        cv.raw_negative_fraction_physical,
                })
                if (rep+1)%10==0 or rep+1==args.replicates:
                    pd.DataFrame(rows).to_csv(detail_file,index=False)

    R=pd.DataFrame(rows)
    summaries=[]
    powers=[]
    for case,gcase in R.groupby("case"):
        for mult,g in gcase.groupby("amplitude_multiplier"):
            n=len(g)
            for criterion,col in [
                ("reference","detected_reference_criterion"),
                ("uniform","detected_uniform_criterion"),
            ]:
                hits=int(g[col].sum())
                lo,hi=wilson_interval(hits,n)
                powers.append({
                    "case":case,"criterion":criterion,
                    "amplitude_multiplier":mult,
                    "injected_global_std_R":float(g.injected_global_std_R.iloc[0]),
                    "hits":hits,"replicates":n,
                    "power":hits/n,"power_wilson_low":lo,"power_wilson_high":hi,
                })

    P=pd.DataFrame(powers)
    P.to_csv(out/"final_power_curves.csv",index=False)
    for (case,criterion),g in P.groupby(["case","criterion"]):
        g=g.sort_values("injected_global_std_R")
        summaries.append({
            "case":case,
            "criterion":criterion,
            "reference_global_std_R":refsigma,
            "reference_tau_star":reftau,
            "false_positive_rate":float(g.loc[
                np.isclose(g.amplitude_multiplier,0),"power"].iloc[0]),
            "U90_global_std_R":crossing(
                g.injected_global_std_R,g.power,0.90),
            "U95_global_std_R":crossing(
                g.injected_global_std_R,g.power,0.95),
            "U90_over_reference":crossing(
                g.amplitude_multiplier,g.power,0.90),
            "U95_over_reference":crossing(
                g.amplitude_multiplier,g.power,0.95),
            "conservative_U90_over_reference":crossing(
                g.amplitude_multiplier,g.power_wilson_low,0.90),
            "max_power":float(g.power.max()),
        })
    S=pd.DataFrame(summaries)
    S.to_csv(out/"final_exclusion_limits.csv",index=False)
    print("\nFINAL EXCLUSION SUMMARY",flush=True)
    print(S.to_string(index=False),flush=True)


if __name__=="__main__":
    main()
