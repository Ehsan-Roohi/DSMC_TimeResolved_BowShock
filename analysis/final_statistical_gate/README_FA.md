# Final statistical gate before manuscript drafting

Copy the entire `JFM2_FINAL_STATISTICAL_GATE` folder into the root of the
existing `JFM2_ALL_KN_UNIFIED_ANALYSIS` folder.

Run:

```powershell
powershell -ExecutionPolicy Bypass `
  -File JFM2_FINAL_STATISTICAL_GATE\RUN_FINAL_STATISTICAL_GATE.ps1 `
  -PowerReplicates 100
```

This stage does not read raw DS2FF files and does not rerun POD. It uses the
existing marker-array outputs.

It performs:

1. sliding-window persistence analysis;
2. injected low-Kn-mode amplitude sweeps;
3. Wilson confidence intervals for detection power;
4. U90 and U95 exclusion limits;
5. two detection criteria:
   - alignment with the Kn=0.01 reference mode;
   - uniform-displacement shape criterion.

The code uses `psd_iterations=0` for synthetic replicates, making it much
faster than the earlier power script. It writes progress after every ten
replicates and resumes from the existing replicate CSV.

The decisive quantity is:

```text
U90_over_reference
```

For a non-detected case:

- `U90_over_reference < 1` means a collective mode as large as the Kn=0.01
  mode would have been detected with at least 90% power;
- `U90_over_reference > 1` means the present data cannot exclude persistence
  of a low-Kn-sized mode.
