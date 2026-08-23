# OpenFOAM MUI DSMC-NS Coupling

This repository modernizes the one-way hybrid `rhoCentralFoam`/`dsmcFoam`
method described by Darbandi and Roohi (*International Journal for Numerical
Methods in Fluids*, 2013, DOI: `10.1002/fld.3769`).

Development is gated. A later physical or production case is never submitted
until the smaller API, transport, conservation, and equilibrium checks pass.

## Current branch: Gate 3A

Gate 0 passed on Unity with OpenFOAM-v2312, OpenMPI 4.1.6, and pinned MUI-v2.
Gate 1A compiled the continuum and DSMC adapter APIs. Gate 1B ran the two real
derived solvers in uniform equilibrium. Gate 1C validated the fixed-interface
flat-plate calculation against full-DSMC sampling uncertainty.

Gate 2 passed in Unity job `63533453`. Its automatic gradient-length Knudsen
interface completed nine forward/reverse frames, dynamically activated and
deactivated 717 cells, preserved retained parcel identities, and limited the
activation mismatch to `0.4874` DSMC sampling standard deviations.

Gate 3 is split to avoid debugging the conservation operator inside an
expensive cylinder run. Gate 3A transfers block-integrated DSMC mass,
momentum, and energy fluxes through MUI's conservative RBF sampler, rejects
statistically unresolved windows, audits raw and relaxed global conservation,
and requires a checkpoint/restart execution to reproduce the continuous
result byte for byte. Gate 3B will embed this accepted contract in the real
adaptive cylinder solvers and perform physical validation and scaling.

## Unity one-line submission

```bash
ROOT=/project/pi_roohie_umass_edu/github_sync/OpenFOAM-MUI-DSMC-NS; BR=mui-dsmc-ns-gate3a; cd "$ROOT" && git fetch origin "$BR:refs/remotes/origin/$BR" && { git checkout "$BR" 2>/dev/null || git checkout -b "$BR" --track "origin/$BR"; } && git merge --ff-only "origin/$BR" && OPENFOAM_MODULE=openfoam/2312 bash scripts/submit_unity_gate3a.sh
```

The command requires the Gate 2 PASS artifact in the same checkout. It prints
the Slurm job ID and exact log path.

## Gate sequence

- Gate 0: environment, MPI ABI, and MUI MPMD transport — passed.
- Gate 1A: v2312 adapter API and equilibrium moment audit — passed.
- Gate 1B: actual two-solver uniform-equilibrium integration — passed.
- Gate 1C: fixed-interface flat-plate physical validation — passed.
- Gate 2: automatic interface, hysteresis, and parcel reuse — passed.
- Gate 3A: conservative flux transfer and restart gate — ready for Unity.
- Gate 3B: adaptive two-way cylinder validation and scaling — gated by 3A.

See [docs/GATES.md](docs/GATES.md) and
[docs/GATE3A.md](docs/GATE3A.md).

## Reproducibility

- MUI is pinned to commit `b130c7a12aa8e7ac8d54e9188c4836342daed263`.
- Gate 3A refuses to run without the Gate 2 PASS artifact.
- Each Slurm job writes to a unique, non-overwriting run directory.
- Relaxation is forbidden for unresolved flux windows.
- Continuous and restarted final states must be byte-identical.
- A machine-readable summary records all conservation errors.

## License

GPL-3.0-or-later. MUI retains its upstream dual Apache-2.0/GPL-3.0 licensing.
