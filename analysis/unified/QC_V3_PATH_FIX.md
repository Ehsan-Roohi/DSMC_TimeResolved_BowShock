
# QC V3 path hotfix

## Cause of the failure

QC wrote the resolved campaign file under the configured external result root:

`G:\Ahmad\project\Cylinder-ML\Results-Kn\ALL_KN_FINAL_ANALYSIS\qc\resolved_campaign_config.json`

The old PowerShell wrapper instead looked for it relative to the package folder:

`..\ALL_KN_FINAL_ANALYSIS\qc\resolved_campaign_config.json`

These are different locations.

## Fix

`RUN_REMAP_PILOT.ps1` now reads `paths.results_root` from the JSON config,
constructs the absolute resolved-config path, and quotes paths safely even when
they contain spaces or `&`.

Because QC has already passed, the user may run:

```powershell
powershell -ExecutionPolicy Bypass -File RUN_REMAP_PILOT_ONLY.ps1
```

or replace the old wrapper and run:

```powershell
powershell -ExecutionPolicy Bypass -File RUN_REMAP_PILOT.ps1
```
