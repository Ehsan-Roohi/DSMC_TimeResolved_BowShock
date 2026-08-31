#!/usr/bin/env python3
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);d=json.loads(p.read_text())
ok=(d.get("gate")=="3M-LONG-MULTI-WINDOW-STABILITY" and d.get("status")=="PASS"
 and d.get("coupled_steps")==10000 and d.get("coupling_windows")==50
 and d.get("selected_rank_layout")=="2+2" and d.get("run_dir"))
if not ok: raise SystemExit(f"Gate 3M prerequisite is not a verified PASS: {p}")
print(f"GATE3M_PREREQUISITE=PASS artifact={p.resolve()}")
