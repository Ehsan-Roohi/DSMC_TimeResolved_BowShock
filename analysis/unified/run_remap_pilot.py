#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys,shlex
from pathlib import Path
import pandas as pd
from campaign_utils import load_json

def run(cmd,dry=False):
    print("\n>>>"," ".join(shlex.quote(str(x)) for x in cmd))
    if not dry:
        subprocess.run(cmd,check=True)

def finite_stat(series, which):
    x=pd.to_numeric(series,errors="coerce").to_numpy(float)
    x=x[pd.notna(x)]
    if len(x)==0:
        return float("nan")
    return float(x.max() if which=="max" else x.min())

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--count",type=int,default=10)
    ap.add_argument("--dry-run",action="store_true")
    a=ap.parse_args()
    cfg=load_json(a.config); here=Path(__file__).resolve().parent
    p=cfg["analysis"]["pod"]
    outroot=Path(cfg["paths"]["results_root"])/"remap_pilot"
    analyzer=here/"analyze_ds2ff_snapshots_shock_attached_v5_wallclip.py"
    for c in cfg["cases"]:
        out=outroot/c["label"]
        cmd=[sys.executable,str(analyzer),"--pattern",c["pattern"],"--out",str(out),
             "--variables","D","--dt-star",str(c["dt_star"]),
             "--start-index",str(c.get("common_start_index",0)),"--count",str(a.count),
             "--theta-min",str(p["theta_min"]),"--theta-max",str(p["theta_max"]),
             "--ntheta",str(p["ntheta"]),"--xi-min",str(p["xi_min"]),
             "--xi-max",str(p["xi_max"]),"--nxi",str(p["nxi"]),
             "--physical-wall-buffer-R",str(p["physical_wall_buffer_R"]),
             "--wall-exclude-R",str(p["marker_wall_exclude_R"]),
             "--marker","halfjump","--width-mode","transition",
             "--input-remap","nearest","--n-pod-modes","3","--dmd-rank","3",
             "--n-dmd-modes","3","--write-mode-fields","0"]
        run(cmd,a.dry_run)

    if a.dry_run: return
    rows=[]
    for c in cfg["cases"]:
        f=outroot/c["label"]/"snapshot_input_grid_qc.csv"
        if not f.exists():
            rows.append({"case":c["label"],"status":"MISSING_QC"}); continue
        d=pd.read_csv(f)
        remap=d.alignment.astype(str).eq("nearest_remap_to_reference")
        rows.append({
            "case":c["label"],"Kn":c["kn"],"status":"PASS",
            "n_tested":len(d),"n_nearest_remapped":int(remap.sum()),
            "remap_fraction":float(remap.mean()),
            "nearest_p95_dist_max":finite_stat(d.nearest_p95_dist,"max"),
            "nearest_max_dist_max":finite_stat(d.nearest_max_dist,"max"),
            "unique_source_fraction_min":finite_stat(d.unique_source_fraction,"min"),
        })
    outroot.mkdir(parents=True,exist_ok=True)
    pd.DataFrame(rows).to_csv(outroot/"remap_pilot_summary.csv",index=False)
    print(pd.DataFrame(rows).to_string(index=False))
if __name__=="__main__": main()
