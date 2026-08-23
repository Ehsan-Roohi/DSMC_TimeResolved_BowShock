# OpenFOAM MUI DSMC-NS Coupling

This repository modernizes the one-way hybrid `rhoCentralFoam`/`dsmcFoam`
method described by Darbandi and Roohi (*International Journal for Numerical
Methods in Fluids*, 2013, DOI: `10.1002/fld.3769`).

Development is gated. A later physical or production case is never submitted
until the smaller API, transport, conservation, and equilibrium checks pass.

## Current branch: Gate 2

Gate 0 passed on Unity with OpenFOAM-v2312, OpenMPI 4.1.6, and pinned MUI-v2.
Gate 1A then compiled the continuum and DSMC adapter APIs and passed the fixed
interface moment audit. Gate 1B now runs real derived OpenFOAM executables:

1. `rhoCentralFoamMUI` advances a uniform periodic monatomic-argon case;
2. `dsmcFoamMUI` receives the continuum state through MUI and constructs the
   six-velocity moment-exact packet in every DSMC cell through
   `dsmcCloud::addNewParcel`;
3. both solvers advance together for ten physical time steps and exchange
   density, velocity, temperature and specific energy at every step; and
4. both independently audit mass, momentum, energy and cross-solver state.

Unity job `63484646` passed all Gate 1B criteria: both solvers completed ten
coupled steps, the maximum conservation errors were `6.31e-34` (continuum)
and `5.71e-16` (DSMC), and the maximum cross-state mismatch was `8.96e-7`.

Gate 1C passed on Unity in resume job `63489859`. The heat-flux and shear
profile differences were respectively `0.3115` and `0.2598` normalized L2;
both were below the full-DSMC sampling thresholds (`0.3882` and `0.3602`).

Gate 2 now replaces the fixed interface with an automatic continuum-breakdown
interface. It evaluates density, temperature, and velocity gradient-length
Knudsen numbers on five real continuum snapshots, applies `0.05/0.03`
activation/deactivation hysteresis, and replays the snapshots forward and
backward. A real v2312 `dsmcCloud` then proves retained parcel identity,
creation only in newly activated cells, removal from deactivated cells, and
activation-state agreement normalized by finite-particle uncertainty.

## Unity one-line submission

```bash
ROOT=/project/pi_roohie_umass_edu/github_sync/OpenFOAM-MUI-DSMC-NS; BR=mui-dsmc-ns-gate2; cd "$ROOT" && git fetch origin "$BR:refs/remotes/origin/$BR" && { git checkout "$BR" 2>/dev/null || git checkout -b "$BR" --track "origin/$BR"; } && git merge --ff-only "origin/$BR" && OPENFOAM_MODULE=openfoam/2312 bash scripts/submit_unity_gate2.sh
```

The command requires the Gate 1C PASS artifact in the same checkout. It prints
the Slurm job ID and exact log path.

## Gate sequence

- Gate 0: environment, MPI ABI, and MUI MPMD transport — passed on Unity.
- Gate 1A: v2312 adapter API plus fixed-interface equilibrium audit — passed.
- Gate 1B: short uniform-equilibrium run with the actual two solvers — passed.
- Gate 1C: fixed-interface flat-plate comparison against full DSMC uncertainty
  — passed on Unity.
- Gate 2: automatic interface with hysteresis and particle reuse — implemented,
  pending Unity evidence.
- Gate 3: conservative two-way coupling.

See [docs/GATES.md](docs/GATES.md), [docs/GATE1A.md](docs/GATE1A.md),
[docs/GATE1B.md](docs/GATE1B.md), [docs/GATE1C.md](docs/GATE1C.md), and
[docs/GATE2.md](docs/GATE2.md).

## Reproducibility

- MUI is pinned to commit `b130c7a12aa8e7ac8d54e9188c4836342daed263`.
- Gate 2 refuses to run without the Gate 1C PASS artifact.
- Cases are generated into a unique, non-overwriting run directory.
- Interface placement uses only continuum fields and predeclared thresholds.
- A machine-readable summary and complete nine-frame indicator CSV are emitted.

## License

GPL-3.0-or-later. MUI retains its upstream dual Apache-2.0/GPL-3.0 licensing.
