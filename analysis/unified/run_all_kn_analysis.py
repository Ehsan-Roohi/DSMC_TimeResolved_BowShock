#!/usr/bin/env python3
from __future__ import annotations
import argparse,subprocess,sys,shlex
from pathlib import Path

def run(cmd,dry=False):
 print("\n###"," ".join(shlex.quote(str(x)) for x in cmd));
 if not dry: subprocess.run(cmd,check=True)

def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--config",default="../config/all_kn_campaign_config.json"); ap.add_argument("--stage",choices=["qc","pod","temporal-common","temporal-full","inference-common","inference-full","power-common","power-full","collect","all"],default="qc"); ap.add_argument("--dry-run",action="store_true"); ap.add_argument("--allow-incomplete",action="store_true"); a=ap.parse_args(); here=Path(__file__).resolve().parent; config=Path(a.config).resolve();
 # QC always creates resolved config
 qc_out=Path(__import__('json').loads(config.read_text(encoding='utf-8'))["paths"]["results_root"])/"qc"; resolved=qc_out/"resolved_campaign_config.json"
 def qc():
  cmd=[sys.executable,str(here/"preflight_qc.py"),"--config",str(config),"--out",str(qc_out)];
  if a.allow_incomplete: cmd.append("--allow-incomplete")
  run(cmd,a.dry_run)
 def need_resolved():
  if not resolved.exists() and not a.dry_run: qc()
  return resolved if resolved.exists() else config
 stages=[a.stage] if a.stage!="all" else ["qc","pod","temporal-common","inference-common","temporal-full","inference-full","power-full","collect"]
 for st in stages:
  if st=="qc": qc(); continue
  cfg=need_resolved()
  if st=="pod": run([sys.executable,str(here/"run_corrected_pod_campaign.py"),"--config",str(cfg)],a.dry_run); run([sys.executable,str(here/"collect_corrected_pod.py"),"--config",str(cfg)],a.dry_run)
  elif st=="temporal-common": run([sys.executable,str(here/"run_temporal_coarse_graining.py"),"--config",str(cfg),"--track","common200"],a.dry_run); run([sys.executable,str(here/"collect_temporal_coarse_graining.py"),"--config",str(cfg),"--track","common200"],a.dry_run)
  elif st=="temporal-full": run([sys.executable,str(here/"run_temporal_coarse_graining.py"),"--config",str(cfg),"--track","full"],a.dry_run); run([sys.executable,str(here/"collect_temporal_coarse_graining.py"),"--config",str(cfg),"--track","full"],a.dry_run)
  elif st=="inference-common": run([sys.executable,str(here/"run_correlated_noise.py"),"--config",str(cfg),"--track","common200"],a.dry_run)
  elif st=="inference-full": run([sys.executable,str(here/"run_correlated_noise.py"),"--config",str(cfg),"--track","full"],a.dry_run)
  elif st=="power-common": run([sys.executable,str(here/"power_exclusion_limits.py"),"--config",str(cfg),"--track","common200"],a.dry_run)
  elif st=="power-full": run([sys.executable,str(here/"power_exclusion_limits.py"),"--config",str(cfg),"--track","full"],a.dry_run)
  elif st=="collect": run([sys.executable,str(here/"master_collect.py"),"--config",str(cfg),"--track","common200"],a.dry_run); run([sys.executable,str(here/"master_collect.py"),"--config",str(cfg),"--track","full"],a.dry_run)
if __name__=="__main__": main()
