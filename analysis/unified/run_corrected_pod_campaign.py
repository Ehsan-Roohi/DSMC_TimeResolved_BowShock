#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys,shlex
from pathlib import Path
from campaign_utils import load_json

DEFAULT_VARS=["D","MA","TTR","TRT","P"]

def complete(out: Path):
    return all((out/x).exists() for x in ["pod_energy.csv","dmd_eigs.csv","shock_window_qc_summary.csv"])

def execute(cmd,out,dry):
    print("\n>>>"," ".join(shlex.quote(str(x)) for x in cmd))
    if complete(out): print("SKIP completed",out); return
    if not dry: subprocess.run(cmd,check=True)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--config",required=True); ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args(); cfg=load_json(a.config); here=Path(__file__).resolve().parent
    p=cfg["analysis"]["pod"]; outroot=Path(cfg["paths"]["results_root"])/"corrected_pod"
    outroot.mkdir(parents=True,exist_ok=True); common_n=int(cfg["analysis"]["common_n"])
    vars_=p.get("variables",DEFAULT_VARS)
    common=["--theta-min",str(p["theta_min"]),"--theta-max",str(p["theta_max"]),"--ntheta",str(p["ntheta"]),
      "--xi-min",str(p["xi_min"]),"--xi-max",str(p["xi_max"]),"--nxi",str(p["nxi"]),
      "--physical-wall-buffer-R",str(p["physical_wall_buffer_R"]),"--wall-exclude-R",str(p["marker_wall_exclude_R"]),
      "--marker","halfjump","--width-mode","transition","--input-remap","nearest",
      "--n-pod-modes",str(p["n_pod_modes"]),"--dmd-rank",str(p["dmd_rank"]),"--n-dmd-modes",str(p["n_dmd_modes"]),
      "--write-mode-fields",str(p["write_mode_fields"])]
    if p.get("do_spod",False):
        common += ["--do-spod","--spod-nfft",str(p["spod_nfft"]),"--spod-overlap",str(p["spod_overlap"]),"--spod-pod-rank",str(p["spod_pod_rank"])]
    analyzer=here/"analyze_ds2ff_snapshots_shock_attached_v5_wallclip.py"
    for case in cfg["cases"]:
        base=[sys.executable,str(analyzer),"--pattern",case["pattern"],"--dt-star",str(case["dt_star"]),*common,
              "--start-index",str(case.get("common_start_index",0)),"--count",str(common_n)]
        if p.get("run_multivariate",True):
            out=outroot/case["label"]/"common200_multivariate"; execute(base+["--out",str(out),"--variables",*vars_],out,a.dry_run)
        if p.get("run_variablewise",True):
            for v in vars_:
                out=outroot/case["label"]/f"common200_{v}"; execute(base+["--out",str(out),"--variables",v],out,a.dry_run)
        if p.get("run_split_half",False):
            split=common_n//2
            for tag,start in [("first_half",0),("second_half",split)]:
                for v in p.get("split_variables",["D","TRT"]):
                    out=outroot/case["label"]/f"{tag}_{v}"
                    cmd=[sys.executable,str(analyzer),"--pattern",case["pattern"],"--dt-star",str(case["dt_star"]),*common,
                         "--start-index",str(case.get("common_start_index",0)+start),"--count",str(split),"--out",str(out),"--variables",v]
                    execute(cmd,out,a.dry_run)
if __name__=="__main__": main()
