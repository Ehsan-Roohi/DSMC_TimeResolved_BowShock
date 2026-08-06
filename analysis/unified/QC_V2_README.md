
# QC V2 update

The original QC treated any change in Tecplot `I=` as a fatal header mismatch.
For adaptive DS2V point clouds this is too strict. The production analyzer
already remaps each snapshot to the reference point cloud and records the
mapping quality.

QC V2 now distinguishes:

- `PASS`: identical point count and compatible variables/format;
- `PASS_REMAP_REQUIRED`: variables and zone format agree, but adaptive point
  counts differ; this is permitted;
- `VARIABLE_MISMATCH`: fatal;
- `ZONE_FORMAT_MISMATCH`: fatal;
- `HEADER_READ_ERROR`: fatal.

Run:

```powershell
powershell -ExecutionPolicy Bypass -File RUN_QC_FIRST.ps1
```

The new table is:

```text
ALL_KN_FINAL_ANALYSIS/qc/preflight_qc_v2.csv
```

Then run the ten-snapshot remap pilot:

```powershell
powershell -ExecutionPolicy Bypass -File RUN_REMAP_PILOT.ps1
```

Inspect:

```text
ALL_KN_FINAL_ANALYSIS/remap_pilot/remap_pilot_summary.csv
```

Only after this pilot should the full campaign be started.
