#!/usr/bin/env python3
from __future__ import annotations
import argparse,glob,json,re
from pathlib import Path
import numpy as np
import pandas as pd
from campaign_utils import load_json,save_json,snapshot_files

TIME_COLUMNS=["time_scaled_center","t_over_sfac","time"]
DTSTAR_COLUMNS=["dt_star_center","dt_star"]
PASS_STATUSES={"PASS","PASS_REMAP_REQUIRED"}

def newest_match(pattern: str|None) -> Path|None:
    if not pattern: return None
    matches=[Path(x) for x in glob.glob(pattern,recursive=True)]
    return max(matches,key=lambda p:p.stat().st_mtime) if matches else None

def read_log(case: dict):
    p=newest_match(case.get("log_pattern"))
    if p is None: return None,None
    df=pd.read_csv(p,skipinitialspace=True)
    if "type" in df:
        snap=df[df["type"].astype(str).str.lower().eq("snapshot")]
        if not snap.empty: df=snap
    return p,df

def positive_median_diff(df: pd.DataFrame):
    for col in TIME_COLUMNS:
        if col in df:
            x=pd.to_numeric(df[col],errors="coerce").to_numpy(float)
            d=np.diff(x[np.isfinite(x)])
            d=d[d>0]
            if len(d): return float(np.median(d)),col
    return None,None

def log_dtstar(df: pd.DataFrame):
    for col in DTSTAR_COLUMNS:
        if col in df:
            x=pd.to_numeric(df[col],errors="coerce").to_numpy(float)
            x=x[np.isfinite(x)&(x>0)]
            if len(x): return float(np.median(x)),col
    return None,None

def header_signature(path: str):
    with open(path,"r",encoding="utf-8",errors="ignore") as f:
        lines=[]
        for _ in range(40):
            line=f.readline()
            if line=="": break
            lines.append(line.strip())
    var_start=next((i for i,l in enumerate(lines) if "VARIABLES" in l.upper()),None)
    zone_start=next((i for i,l in enumerate(lines) if l.upper().startswith("ZONE")),None)
    if var_start is None or zone_start is None:
        raise ValueError("VARIABLES or ZONE line missing from first 40 lines")
    var_text=" ".join(lines[var_start:zone_start])
    vars_=re.findall(r'"([^"]+)"',var_text)
    if not vars_:
        vars_=[v.strip().strip(",") for v in var_text.split("=",1)[-1].split()
               if v.strip().strip(",")]
    zone_line=lines[zone_start]
    mi=re.search(r"\bI\s*=\s*(\d+)",zone_line,re.I)
    mj=re.search(r"\bJ\s*=\s*(\d+)",zone_line,re.I)
    mk=re.search(r"\bK\s*=\s*(\d+)",zone_line,re.I)
    fmt=re.search(r"\bF\s*=\s*([A-Z]+)",zone_line,re.I)
    return {
        "variables":vars_,
        "I":int(mi.group(1)) if mi else None,
        "J":int(mj.group(1)) if mj else None,
        "K":int(mk.group(1)) if mk else None,
        "format":fmt.group(1).upper() if fmt else None,
        "zone_line":zone_line,
    }

def inspect_all_headers(files):
    sigs=[]; errors=[]
    for f in files:
        try:
            s=header_signature(f); s["file"]=f; sigs.append(s)
        except Exception as e:
            errors.append({"file":f,"error":str(e)})
    if not sigs:
        return {},errors
    ref=sigs[0]
    vars_ok=all(s["variables"]==ref["variables"] for s in sigs)
    fmt_ok=all(s["format"]==ref["format"] for s in sigs)
    jk_ok=all((s["J"],s["K"])==(ref["J"],ref["K"]) for s in sigs)
    ipoints=np.array([s["I"] for s in sigs if s["I"] is not None],dtype=int)
    return {
        "variables_reference":ref["variables"],
        "format_reference":ref["format"],
        "J_reference":ref["J"],"K_reference":ref["K"],
        "variable_list_consistent":vars_ok,
        "format_consistent":fmt_ok,
        "JK_consistent":jk_ok,
        "npoints_min":int(ipoints.min()) if len(ipoints) else None,
        "npoints_median":float(np.median(ipoints)) if len(ipoints) else None,
        "npoints_max":int(ipoints.max()) if len(ipoints) else None,
        "npoints_unique_count":int(len(np.unique(ipoints))) if len(ipoints) else 0,
        "npoints_consistent":bool(len(np.unique(ipoints))<=1) if len(ipoints) else False,
        "remap_required":bool(len(np.unique(ipoints))>1) if len(ipoints) else False,
        "n_headers_read":len(sigs),
    },errors

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--config",required=True)
    ap.add_argument("--out",required=True)
    ap.add_argument("--allow-incomplete",action="store_true")
    args=ap.parse_args()
    cfg=load_json(args.config)
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    diameter=float(cfg["geometry"]["diameter_m"])
    common_n=int(cfg["analysis"]["common_n"])

    cache={}; urefs=[]
    for c in cfg["cases"]:
        lp,df=read_log(c)
        rawdt,col=positive_median_diff(df) if df is not None else (None,None)
        direct,dcol=log_dtstar(df) if df is not None else (None,None)
        cache[c["label"]]=(lp,df,rawdt,col,direct,dcol)
        if rawdt and c.get("dt_star") not in (None,""):
            urefs.append(float(c["dt_star"])*diameter/rawdt)
    default_u=cfg.get("freestream",{}).get("u_inf_m_s")
    if default_u in (None,"") and urefs:
        default_u=float(np.median(urefs))

    rows=[]; resolved=[]; fatal=[]
    for c0 in cfg["cases"]:
        c=dict(c0); files=snapshot_files(c); n=len(files)
        lp,df,rawdt,tcol,direct,dcol=cache[c["label"]]
        dt=c.get("dt_star"); source="config"
        if dt in (None,""):
            if direct is not None:
                dt=direct; source=f"log:{dcol}"
            else:
                u=c.get("u_inf_m_s") or default_u
                if rawdt is not None and u not in (None,""):
                    dt=rawdt*float(u)/diameter; source=f"log:{tcol}+Uinf"
        if dt in (None,""):
            fatal.append(f"{c['label']}: dt_star unresolved; provide dt_star, v10 log, or Uinf.")
            dt=float("nan")
        c["dt_star"]=float(dt); c["available_snapshots"]=n; c["common_count"]=common_n
        resolved.append(c)

        sizes=[Path(f).stat().st_size for f in files] if files else []
        h,errors=inspect_all_headers(files)
        (out/f"{c['label']}_header_audit.json").write_text(
            json.dumps({"summary":h,"errors":errors},indent=2),encoding="utf-8")

        status="PASS"
        if n==0: status="NO_FILES"
        elif n<common_n: status="INCOMPLETE_COMMON_N"
        elif errors: status="HEADER_READ_ERROR"
        elif not h.get("variable_list_consistent",False): status="VARIABLE_MISMATCH"
        elif not h.get("format_consistent",False) or not h.get("JK_consistent",False):
            status="ZONE_FORMAT_MISMATCH"
        elif h.get("remap_required",False):
            status="PASS_REMAP_REQUIRED"

        cadence_flag="OK"
        if np.isfinite(dt):
            if dt<0.20: cadence_flag="FINE"
            elif dt>0.60: cadence_flag="COARSE"
            elif dt>0.45: cadence_flag="SLIGHTLY_COARSE"

        rows.append({
            "case":c["label"],"Kn":c["kn"],"n_files":n,"required_common_n":common_n,
            "status":status,"dt_star":dt,"dt_star_source":source,
            "cadence_flag":cadence_flag,"log_file":str(lp or ""),"log_rows":len(df) if df is not None else 0,
            "median_raw_time_spacing":rawdt,"time_column":tcol,
            "min_file_MB":min(sizes)/2**20 if sizes else np.nan,
            "median_file_MB":np.median(sizes)/2**20 if sizes else np.nan,
            "max_file_MB":max(sizes)/2**20 if sizes else np.nan,
            "variable_list_consistent":h.get("variable_list_consistent",False),
            "format_consistent":h.get("format_consistent",False),
            "npoints_consistent":h.get("npoints_consistent",False),
            "npoints_min":h.get("npoints_min"),"npoints_median":h.get("npoints_median"),
            "npoints_max":h.get("npoints_max"),
            "npoints_unique_count":h.get("npoints_unique_count",0),
            "remap_required":h.get("remap_required",False),
            "header_read_errors":len(errors),
            "first_file":files[0] if files else "","last_file":files[-1] if files else "",
        })

    q=pd.DataFrame(rows).sort_values("Kn")
    q.to_csv(out/"preflight_qc_v2.csv",index=False)
    cfg["cases"]=resolved
    cfg.setdefault("freestream",{})["u_inf_m_s_calibrated_or_configured"]=default_u
    save_json(cfg,out/"resolved_campaign_config.json")
    print(q.to_string(index=False))
    if fatal: raise SystemExit("\n".join(fatal))
    bad=q[~q.status.isin(PASS_STATUSES)]
    if not bad.empty and not args.allow_incomplete:
        raise SystemExit("Preflight V2 failed. See preflight_qc_v2.csv.")
    print("PREFLIGHT V2 PASS")
if __name__=="__main__": main()
