#!/usr/bin/env python3
import json,sys
from pathlib import Path
p=Path(sys.argv[1]); d=json.loads(p.read_text())
ok=(d.get("gate")=="3K-DISTRIBUTED-CHECKPOINT-RESTART" and d.get("status")=="PASS"
 and d.get("restart_has_no_duplicated_or_missing_step") is True
 and d.get("decomposed_openfoam_fields_and_cloud_restarted") is True
 and d.get("dynamic_layer_and_reservoir_state_restored") is True
 and d.get("unique_interface_ownership_after_restart") is True
 and d.get("global_wall_flux_reduction_after_restart") is True
 and d.get("maximum_particle_ownership_balance_error")==0
 and d.get("maximum_inactive_parcels")==0
 and d.get("restart_matches_continuous_within_sampling_tolerance") is True
 and d.get("distributed_scaling_completed") is False)
if not ok: raise SystemExit(f"Gate 3K prerequisite is not a verified PASS: {p}")
print(f"GATE3K_PREREQUISITE=PASS artifact={p.resolve()}")
