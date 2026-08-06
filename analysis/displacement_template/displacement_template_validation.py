#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gc
import json
import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import analyze_ds2ff_snapshots_shock_attached_v5_wallclip as shock
from campaign_utils import load_json, snapshot_files


DEFAULT_CASES = ["Kn0p01", "Kn0p025", "Kn0p050"]
DEFAULT_VARIABLES = ["D", "MA", "TTR", "P"]


def finite_gradient_along_s(mean_field: np.ndarray, swin: np.ndarray) -> np.ndarray:
    out=np.full_like(mean_field,np.nan,dtype=float)
    for j in range(mean_field.shape[0]):
        good=np.isfinite(mean_field[j]) & np.isfinite(swin[j])
        idx=np.where(good)[0]
        if len(idx)<5:
            continue
        # Work on contiguous finite segments.
        breaks=np.where(np.diff(idx)>1)[0]
        starts=np.r_[0,breaks+1]
        ends=np.r_[breaks,len(idx)-1]
        for a,b in zip(starts,ends):
            ii=idx[a:b+1]
            if len(ii)>=5:
                out[j,ii]=np.gradient(mean_field[j,ii],swin[j,ii])
    return out


def reference_envelope(theta: np.ndarray, csv_path: Path | None) -> np.ndarray:
    if csv_path is None or not csv_path.exists():
        return np.ones_like(theta,dtype=float)
    d=pd.read_csv(csv_path)
    v=np.interp(theta,d["theta_deg"].to_numpy(float),
                d["physical_mode1"].to_numpy(float))
    if np.nanmean(v)<0:
        v=-v
    m=float(np.nanmean(v))
    if abs(m)<1e-10:
        v=v/np.sqrt(np.nanmean(v*v))
    else:
        v=v/m
    return v


def density_weights(gd: np.ndarray, valid: np.ndarray,
                    grad_fraction: float, power: float) -> np.ndarray:
    w=np.zeros_like(gd,dtype=float)
    for j in range(gd.shape[0]):
        a=np.abs(gd[j])
        good=valid[j] & np.isfinite(a)
        if not np.any(good):
            continue
        amax=float(np.nanmax(a[good]))
        if not np.isfinite(amax) or amax<=0:
            continue
        support=good & (a>=grad_fraction*amax)
        if np.count_nonzero(support)<4:
            order=np.argsort(a[good])
            ids=np.where(good)[0][order[-min(8,len(order)):]]
            support=np.zeros_like(good)
            support[ids]=True
        ww=np.zeros_like(a)
        ww[support]=(a[support]/amax)**power
        s=float(np.sum(ww))
        if s>0:
            # Equal total weight per valid ray.
            w[j]=ww/s
    total=float(np.sum(w))
    return w/total if total>0 else w


def weighted_projection(qprime: np.ndarray, template: np.ndarray,
                        weights: np.ndarray):
    ns=qprime.shape[0]
    amp=np.full(ns,np.nan)
    corr=np.full(ns,np.nan)
    frac=np.full(ns,np.nan)
    denom=float(np.nansum(weights*template*template))
    if not np.isfinite(denom) or denom<=1e-300:
        return amp,corr,frac
    for k in range(ns):
        q=qprime[k]
        good=np.isfinite(q)&np.isfinite(template)&np.isfinite(weights)&(weights>0)
        if np.count_nonzero(good)<20:
            continue
        w=weights[good]; t=template[good]; qq=q[good]
        den=float(np.sum(w*t*t))
        qnorm=float(np.sum(w*qq*qq))
        if den<=1e-300 or qnorm<=1e-300:
            continue
        num=float(np.sum(w*t*qq))
        amp[k]=num/den
        corr[k]=num/math.sqrt(den*qnorm)
        frac[k]=max(0.0,min(1.0,num*num/(den*qnorm)))
    return amp,corr,frac


def per_ray_projection(qprime: np.ndarray, template: np.ndarray,
                       weights: np.ndarray) -> np.ndarray:
    ns,ntheta,_=qprime.shape
    out=np.full((ns,ntheta),np.nan)
    for j in range(ntheta):
        w=weights[j]
        good0=np.isfinite(template[j])&np.isfinite(w)&(w>0)
        if np.count_nonzero(good0)<4:
            continue
        t=template[j,good0]
        ww=w[good0]
        den=float(np.sum(ww*t*t))
        if den<=1e-300:
            continue
        for k in range(ns):
            q=qprime[k,j,good0]
            good=np.isfinite(q)
            if np.count_nonzero(good)<4:
                continue
            out[k,j]=float(np.sum(ww[good]*t[good]*q[good])/
                           np.sum(ww[good]*t[good]*t[good]))
    return out


def fit_marker_amplitude(marker_npz: Path, theta: np.ndarray,
                         envelope: np.ndarray, n: int) -> np.ndarray:
    z=np.load(marker_npz)
    th=np.asarray(z["theta_deg"],float)
    s=np.asarray(z["s50_over_R"],float)
    if len(s)<n:
        n=len(s)
    s=s[:n]
    interp=np.full((n,len(theta)),np.nan)
    for k in range(n):
        good=np.isfinite(s[k])
        if np.count_nonzero(good)>=2:
            interp[k]=np.interp(theta,th[good],s[k,good])
    fluct=interp-np.nanmean(interp,axis=0,keepdims=True)
    den=float(np.nansum(envelope*envelope))
    return np.nansum(fluct*envelope[None,:],axis=1)/den


def block_indices(n: int, block: int, rng: np.random.Generator):
    starts=np.arange(0,n-block+1)
    out=[]
    while len(out)<n:
        s=int(rng.choice(starts))
        out.extend(range(s,s+block))
    return np.asarray(out[:n],int)


def safe_corr(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float)
    good=np.isfinite(a)&np.isfinite(b)
    if np.count_nonzero(good)<5:
        return np.nan
    aa=a[good]-np.mean(a[good]); bb=b[good]-np.mean(b[good])
    den=np.linalg.norm(aa)*np.linalg.norm(bb)
    return float(np.dot(aa,bb)/den) if den>0 else np.nan


def bootstrap_corr(a,b,block,nboot,seed):
    rng=np.random.default_rng(seed)
    vals=[]
    n=min(len(a),len(b))
    a=np.asarray(a[:n]); b=np.asarray(b[:n])
    for _ in range(nboot):
        idx=block_indices(n,min(block,n),rng)
        vals.append(safe_corr(a[idx],b[idx]))
    vals=np.asarray(vals,float)
    return (float(np.nanquantile(vals,.025)),
            float(np.nanmedian(vals)),
            float(np.nanquantile(vals,.975)))


def circular_shift_pvalue(a,b,min_shift=8):
    n=min(len(a),len(b))
    a=np.asarray(a[:n]); b=np.asarray(b[:n])
    obs=abs(safe_corr(a,b))
    null=[]
    for s in range(min_shift,max(min_shift+1,n-min_shift)):
        null.append(abs(safe_corr(a,np.roll(b,s))))
    if not null:
        return np.nan
    null=np.asarray(null,float)
    return float((1+np.count_nonzero(null>=obs))/(1+len(null)))


def ar1_timescale(x,dt):
    x=np.asarray(x,float)
    good=np.isfinite(x)
    x=x[good]
    if len(x)<5:
        return np.nan,np.nan
    phi=safe_corr(x[:-1],x[1:])
    tau=(-dt/math.log(phi)) if np.isfinite(phi) and 0<phi<1 else np.nan
    return phi,tau


def shifted_template(template: np.ndarray, xi: np.ndarray, shift: float):
    out=np.full_like(template,np.nan)
    for j in range(template.shape[0]):
        good=np.isfinite(template[j])
        if np.count_nonzero(good)>=3:
            out[j]=np.interp(xi-shift,xi[good],template[j,good],
                             left=np.nan,right=np.nan)
    return out


def read_case_cube(case: dict, cfg: dict, out: Path, count: int,
                   variables: list[str], reuse_cache: bool):
    cache=out/"attached_field_cache.npz"
    if reuse_cache and cache.exists():
        z=np.load(cache,allow_pickle=True)
        return {
            "cube":z["cube"].astype(float),
            "theta":z["theta"],
            "xi":z["xi"],
            "swin":z["swin"],
            "xwin":z["xwin"],
            "ywin":z["ywin"],
            "variables":[str(x) for x in z["variables"]],
            "files":[str(x) for x in z["files"]],
        }

    files=snapshot_files(case)
    start=int(case.get("common_start_index",0))
    files=files[start:start+count]
    if len(files)<count:
        raise ValueError(f"{case['label']}: requested {count}, found {len(files)}")

    print(f"{case['label']}: reading {len(files)} raw snapshots",flush=True)
    all_vars=None
    ref_zones=None
    ref_xy=None
    values=[]
    qc=[]
    load_variables=variables if "D" in variables else ["D"]+variables

    for k,f in enumerate(files):
        vars_,zones=shock.read_tecplot_point_file(f)
        if all_vars is None:
            all_vars=vars_
            ref_zones=zones
            zone_index=0
            xidx=all_vars.index("X"); yidx=all_vars.index("Y")
            vidx=[all_vars.index(v) for v in load_variables]
            ref_xy=zones[zone_index].data[:,[xidx,yidx]]
        elif vars_!=all_vars:
            raise ValueError(f"Variable list mismatch in {f}")
        aligned,info=shock.validate_or_remap_to_reference(
            f,zones,ref_zones,0,vidx,(xidx,yidx),
            1e-10,1e-8,"nearest"
        )
        values.append(aligned.astype(np.float32))
        info["snapshot_index"]=k+1
        qc.append(info)
        if (k+1)%25==0 or k+1==len(files):
            print(f"  loaded {k+1}/{len(files)}",flush=True)

    snapshots=np.stack(values,axis=0)
    pd.DataFrame(qc).to_csv(out/"snapshot_input_grid_qc.csv",index=False)

    pod=cfg["analysis"]["pod"]
    R=float(cfg["geometry"]["diameter_m"])/2.0
    xc=R; yc=0.0
    theta=np.linspace(float(pod["theta_min"]),float(pod["theta_max"]),
                      int(pod["ntheta"]))
    xi=np.linspace(float(pod["xi_min"]),float(pod["xi_max"]),
                   int(pod["nxi"]))
    rho_mean=np.nanmean(snapshots[:,:,load_variables.index("D")],axis=0)
    _,metrics=shock.compute_mean_density_metrics(
        ref_xy,rho_mean,xc,yc,R,theta,
        900,8.0,float(pod["marker_wall_exclude_R"]),4.0,0.94,
        "halfjump","transition",0.5,0.1,0.9,0.03,0.25
    )
    ray_ok=(np.isfinite(metrics["s_peak"])&
            np.isfinite(metrics["delta_rho"])&
            (metrics["delta_rho"]>0)&
            (np.asarray(metrics["valid_fraction"])>=0.05))
    theta=theta[ray_ok]
    for key in list(metrics):
        metrics[key]=np.asarray(metrics[key])[ray_ok]

    cube,xwin,ywin,swin=shock.sample_attached_snapshots(
        ref_xy,snapshots,load_variables,xc,yc,R,theta,xi,
        metrics["s_peak"],metrics["delta_rho"],"linear",
        physical_wall_buffer_R=float(pod["physical_wall_buffer_R"])
    )
    cube=cube.astype(np.float32)
    np.savez_compressed(
        cache,cube=cube,theta=theta,xi=xi,swin=swin,xwin=xwin,ywin=ywin,
        variables=np.asarray(load_variables),files=np.asarray(files)
    )
    pd.DataFrame({
        "theta_deg":theta,
        "s_peak_over_R":metrics["s_peak"]/R,
        "delta_over_R":metrics["delta_rho"]/R,
    }).to_csv(out/"registration_metrics.csv",index=False)
    return {
        "cube":cube.astype(float),"theta":theta,"xi":xi,"swin":swin,
        "xwin":xwin,"ywin":ywin,"variables":load_variables,"files":files
    }


def analyze_case(case: dict, cfg: dict, result_root: Path, out: Path,
                 count: int, variables: list[str], nboot: int,
                 block: int, grad_fraction: float, weight_power: float,
                 reuse_cache: bool):
    out.mkdir(parents=True,exist_ok=True)
    data=read_case_cube(case,cfg,out,count,variables,reuse_cache)
    cube=data["cube"]; theta=data["theta"]; xi=data["xi"]; swin=data["swin"]
    names=data["variables"]
    R=float(cfg["geometry"]["diameter_m"])/2.0
    dt=float(case["dt_star"])

    ref_mode_path=result_root/"correlated_common200"/"Kn0p01"/"ang1"/"physical_mode1.csv"
    env=reference_envelope(theta,ref_mode_path)
    uniform=np.ones_like(theta)
    marker_path=result_root/"temporal_common200"/case["label"]/"marker_arrays_m1_ang1.npz"
    marker=fit_marker_amplitude(marker_path,theta,env,count)

    means=np.nanmean(cube,axis=0)
    grads=np.stack([finite_gradient_along_s(means[i],swin)
                    for i in range(len(names))],axis=0)
    gd=grads[names.index("D")]
    physical=np.isfinite(swin)
    weights=density_weights(gd,physical,grad_fraction,weight_power)

    rows=[]; series={"marker_over_R":marker}
    per_ray={}
    shifted_rows=[]
    recon_data=None

    for vi,var in enumerate(names):
        if var not in variables:
            continue
        qprime=cube[:,vi]-means[vi][None,:,:]
        base=-grads[vi]
        templates={
            "reference_mode":env[:,None]*base,
            "uniform":uniform[:,None]*base,
        }
        for tname,tpl in templates.items():
            amp,corr,frac=weighted_projection(qprime,tpl,weights)
            ampR=amp/R
            series[f"{var}_{tname}_amp_over_R"]=ampR
            series[f"{var}_{tname}_spatial_corr"]=corr
            series[f"{var}_{tname}_projection_fraction"]=frac
            if tname=="reference_mode":
                per_ray[var]=per_ray_projection(qprime,tpl,weights)/R
                ci=bootstrap_corr(ampR,marker,block,nboot,
                                  20000+vi*100+int(round(case["kn"]*10000)))
                p=circular_shift_pvalue(ampR,marker,block)
                phi,tau=ar1_timescale(ampR,dt)
                rows.append({
                    "case":case["label"],"Kn":case["kn"],"variable":var,
                    "template":tname,
                    "field_marker_corr":safe_corr(ampR,marker),
                    "field_marker_corr_q025":ci[0],
                    "field_marker_corr_median":ci[1],
                    "field_marker_corr_q975":ci[2],
                    "circular_shift_pvalue":p,
                    "median_abs_spatial_corr":float(np.nanmedian(np.abs(corr))),
                    "median_projection_fraction":float(np.nanmedian(frac)),
                    "amplitude_std_over_R":float(np.nanstd(ampR,ddof=1)),
                    "marker_std_over_R":float(np.nanstd(marker,ddof=1)),
                    "lag1_phi":phi,"tau_star":tau,
                })
                for shift in [-1.0,-0.5,0.0,0.5,1.0]:
                    st=shifted_template(tpl,xi,shift)
                    _,_,sf=weighted_projection(qprime,st,weights)
                    shifted_rows.append({
                        "case":case["label"],"Kn":case["kn"],
                        "variable":var,"xi_shift":shift,
                        "median_projection_fraction":float(np.nanmedian(sf))
                    })
                if var=="D":
                    k=int(np.nanargmax(np.abs(marker)))
                    ahat=amp[k]
                    recon=ahat*tpl
                    recon_data=(qprime[k],recon,qprime[k]-recon,k)

    ts=pd.DataFrame(series)
    ts.insert(0,"snapshot",np.arange(1,len(ts)+1))
    ts.insert(1,"time_star",np.arange(len(ts))*dt)
    ts.to_csv(out/"displacement_amplitude_timeseries.csv",index=False)
    pd.DataFrame(rows).to_csv(out/"displacement_template_metrics.csv",index=False)
    pd.DataFrame(shifted_rows).to_csv(out/"template_shift_null.csv",index=False)

    # Cross-variable consensus.
    amp_cols=[f"{v}_reference_mode_amp_over_R" for v in variables]
    A=ts[amp_cols].to_numpy(float)
    good=np.all(np.isfinite(A),axis=1)&np.isfinite(marker)
    consensus={}
    if np.count_nonzero(good)>=10:
        Z=A[good]
        Z=(Z-Z.mean(axis=0))/np.maximum(Z.std(axis=0,ddof=1),1e-12)
        U,S,Vt=np.linalg.svd(Z,full_matrices=False)
        pc=U[:,0]*S[0]
        if safe_corr(pc,marker[good])<0:
            pc=-pc
        consensus={
            "case":case["label"],"Kn":case["kn"],
            "field_pc1_variance_fraction":float(S[0]**2/np.sum(S**2)),
            "field_pc1_marker_correlation":safe_corr(pc,marker[good]),
            "median_cross_variable_correlation":
                float(np.nanmedian(np.corrcoef(Z,rowvar=False)[np.triu_indices(len(variables),1)])),
        }
    pd.DataFrame([consensus]).to_csv(out/"multimoment_consensus.csv",index=False)

    # Correlation matrix figure.
    corr_cols=["marker_over_R"]+amp_cols
    C=ts[corr_cols].corr()
    C.to_csv(out/"amplitude_correlation_matrix.csv")
    fig,ax=plt.subplots(figsize=(7,6))
    im=ax.imshow(C.to_numpy(),vmin=-1,vmax=1,cmap="coolwarm")
    ax.set_xticks(range(len(C)),C.columns,rotation=45,ha="right",fontsize=8)
    ax.set_yticks(range(len(C)),C.index,fontsize=8)
    ax.set_title(f"{case['label']}: displacement-amplitude correlations")
    fig.colorbar(im,ax=ax,label="correlation")
    fig.tight_layout()
    fig.savefig(out/"Fig_amplitude_correlation_matrix.png",dpi=300)
    plt.close(fig)

    # Standardized time series.
    fig,ax=plt.subplots(figsize=(10,5))
    for col in corr_cols:
        x=ts[col].to_numpy(float)
        z=(x-np.nanmean(x))/max(np.nanstd(x),1e-12)
        ax.plot(ts.time_star,z,label=col)
    ax.set_xlabel(r"$t^*$"); ax.set_ylabel("standardized amplitude")
    ax.set_title(f"{case['label']}: marker and full-field displacement amplitudes")
    ax.grid(True,alpha=.25); ax.legend(ncol=3,fontsize=7)
    fig.tight_layout()
    fig.savefig(out/"Fig_displacement_timeseries.png",dpi=300)
    plt.close(fig)

    # Template contours.
    fig,axes=plt.subplots(2,2,figsize=(11,7.5),constrained_layout=True)
    for ax,var in zip(axes.ravel(),variables):
        vi=names.index(var)
        tpl=env[:,None]*(-grads[vi])
        q=np.nanpercentile(np.abs(tpl[np.isfinite(tpl)]),99)
        im=ax.contourf(xi,theta,tpl,levels=np.linspace(-q,q,61),
                       cmap="coolwarm",extend="both")
        ax.set_xlabel(r"$\xi$"); ax.set_ylabel(r"$\theta$ [deg]")
        ax.set_title(var)
        fig.colorbar(im,ax=ax,shrink=.8)
    fig.suptitle(f"{case['label']}: full-field displacement templates")
    fig.savefig(out/"Fig_displacement_template_contours.png",dpi=300)
    plt.close(fig)

    # Density reconstruction example.
    if recon_data is not None:
        actual,recon,residual,k=recon_data
        q=max(np.nanpercentile(np.abs(actual[np.isfinite(actual)]),99),1e-12)
        fig,axes=plt.subplots(1,3,figsize=(14,4.2),constrained_layout=True)
        for ax,z,title in zip(axes,[actual,recon,residual],
                              ["Actual density fluctuation",
                               "Displacement-template reconstruction",
                               "Residual"]):
            im=ax.contourf(xi,theta,z,levels=np.linspace(-q,q,61),
                           cmap="coolwarm",extend="both")
            ax.set_xlabel(r"$\xi$"); ax.set_ylabel(r"$\theta$ [deg]")
            ax.set_title(title)
        fig.colorbar(im,ax=axes.ravel().tolist(),shrink=.8)
        fig.suptitle(f"{case['label']}, snapshot {k+1}")
        fig.savefig(out/"Fig_density_reconstruction_example.png",dpi=300)
        plt.close(fig)

    # Save compact field objects for review, not all snapshots.
    np.savez_compressed(
        out/"displacement_template_fields.npz",
        theta_deg=theta,xi=xi,s_over_R=swin/R,
        reference_envelope=env,density_weights=weights,
        mean_fields=means,mean_gradients_per_m=grads,
        variables=np.asarray(names)
    )
    (out/"CASE_DONE.flag").write_text("DONE\n",encoding="utf-8")
    del cube
    gc.collect()
    return rows,consensus


def self_test():
    rng=np.random.default_rng(123)
    ns,nt,nx=240,40,100
    theta=np.linspace(120,179,nt)
    xi=np.linspace(-1,3,nx)
    s=np.tile(xi,(nt,1))
    env=1+0.25*np.cos(np.deg2rad(theta-150))
    mean=1/(1+np.exp(5*xi))[None,:]
    mean=np.repeat(mean,nt,axis=0)
    grad=finite_gradient_along_s(mean,s)
    template=env[:,None]*(-grad)
    a=0.02*np.sin(np.arange(ns)*0.15)
    q=mean[None,:,:]+a[:,None,None]*template[None,:,:]
    q+=0.003*rng.standard_normal(q.shape)
    gd=grad
    w=density_weights(gd,np.isfinite(s),.10,1.0)
    ahat,corr,frac=weighted_projection(q-q.mean(axis=0),template,w)
    assert safe_corr(ahat,a)>0.95
    assert np.nanmedian(np.abs(corr))>0.75
    print("SELF-TEST PASS")


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config")
    ap.add_argument("--out")
    ap.add_argument("--cases",nargs="+",default=DEFAULT_CASES)
    ap.add_argument("--variables",nargs="+",default=DEFAULT_VARIABLES)
    ap.add_argument("--count",type=int,default=200)
    ap.add_argument("--bootstrap",type=int,default=500)
    ap.add_argument("--block",type=int,default=8)
    ap.add_argument("--grad-fraction",type=float,default=0.10)
    ap.add_argument("--weight-power",type=float,default=1.0)
    ap.add_argument("--reuse-cache",action="store_true")
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test:
        self_test(); return
    if not args.config or not args.out:
        ap.error("--config and --out are required")

    cfg=load_json(args.config)
    result_root=Path(cfg["paths"]["results_root"])
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    cases={c["label"]:c for c in cfg["cases"]}
    all_rows=[]; consensus=[]
    for label in args.cases:
        if label not in cases:
            raise SystemExit(f"Case {label} not found in config")
        case_out=out/label
        print(f"\n===== {label} =====",flush=True)
        rows,con=analyze_case(
            cases[label],cfg,result_root,case_out,args.count,args.variables,
            args.bootstrap,args.block,args.grad_fraction,args.weight_power,
            args.reuse_cache
        )
        all_rows.extend(rows); consensus.append(con)

    M=pd.DataFrame(all_rows)
    M.to_csv(out/"all_cases_displacement_template_metrics.csv",index=False)
    C=pd.DataFrame(consensus)
    C.to_csv(out/"all_cases_multimoment_consensus.csv",index=False)

    # Summary figures.
    fig,ax=plt.subplots(figsize=(8,5))
    for var,g in M.groupby("variable"):
        g=g.sort_values("Kn")
        ax.semilogx(g.Kn,g.field_marker_corr,marker="o",label=var)
        ax.fill_between(g.Kn,g.field_marker_corr_q025,
                        g.field_marker_corr_q975,alpha=.15)
    ax.axhline(0,linewidth=1)
    ax.set_xlabel("Kn"); ax.set_ylabel("Field-template / marker correlation")
    ax.set_title("Full-field validation of the collective displacement coordinate")
    ax.grid(True,alpha=.3); ax.legend()
    fig.tight_layout()
    fig.savefig(out/"Fig_summary_field_marker_correlation.png",dpi=300)
    plt.close(fig)

    fig,ax=plt.subplots(figsize=(8,5))
    for var,g in M.groupby("variable"):
        g=g.sort_values("Kn")
        ax.semilogx(g.Kn,100*g.median_projection_fraction,
                    marker="o",label=var)
    ax.set_xlabel("Kn"); ax.set_ylabel("Median template projection fraction [%]")
    ax.set_title("Fraction of field fluctuation aligned with translation template")
    ax.grid(True,alpha=.3); ax.legend()
    fig.tight_layout()
    fig.savefig(out/"Fig_summary_projection_fraction.png",dpi=300)
    plt.close(fig)

    print("\nANALYSIS COMPLETE")
    print(M[["case","variable","field_marker_corr",
             "field_marker_corr_q025","field_marker_corr_q975",
             "median_projection_fraction","circular_shift_pvalue"]].to_string(index=False))


if __name__=="__main__":
    main()
