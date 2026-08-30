#!/usr/bin/env python3
import json,sys
from pathlib import Path
p=Path(sys.argv[1]);d=json.loads(p.read_text())
rows=d.get("scaling",[])
ok=(d.get("gate")=="3L-WHOLE-SOLVER-STRONG-SCALING" and d.get("status")=="PASS"
 and d.get("whole_solver_spatial_scaling_completed") is True
 and d.get("unique_interface_ownership_all_layouts") is True
 and d.get("global_wall_flux_reduction_all_layouts") is True
 and d.get("maximum_particle_ownership_balance_error")==0
 and d.get("maximum_inactive_parcels")==0
 and [r.get("ranks_per_solver") for r in rows]==[1,2,4]
 and d.get("selected_production_layout")=="2+2")
if not ok: raise SystemExit(f"Gate 3L prerequisite is not a verified PASS: {p}")
print(f"GATE3L_PREREQUISITE=PASS artifact={p.resolve()} selected_layout=2+2")
