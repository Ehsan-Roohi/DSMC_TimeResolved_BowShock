# OpenFOAM MUI DSMC-NS Coupling

This repository modernizes the one-way hybrid `rhoCentralFoam`/`dsmcFoam`
method described by Darbandi and Roohi (*International Journal for Numerical
Methods in Fluids*, 2013, DOI: `10.1002/fld.3769`).

Development is gated. A later physical or production case is never submitted
until the smaller API, transport, conservation, and equilibrium checks pass.

## Current branch: Gate 1B

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

This gate tests real solver integration in uniform equilibrium. It does not
claim flat-plate, shock, wall-heat-flux or shear validation.

## Unity one-line submission

```bash
ROOT=/project/pi_roohie_umass_edu/github_sync/OpenFOAM-MUI-DSMC-NS; cd "$ROOT" && git fetch origin && git checkout mui-dsmc-ns-gate1b && git pull --ff-only origin mui-dsmc-ns-gate1b && OPENFOAM_MODULE=openfoam/2312 bash scripts/submit_unity_gate1b.sh
```

The command requires the Gate 1A PASS artifact in the same checkout. It prints
the Slurm job ID and exact log path.

## Gate sequence

- Gate 0: environment, MPI ABI, and MUI MPMD transport — passed on Unity.
- Gate 1A: v2312 adapter API plus fixed-interface equilibrium audit — passed.
- Gate 1B: short uniform-equilibrium run with the actual two solvers — current.
- Gate 1C: flat-plate comparison against full DSMC uncertainty.
- Gate 2: automatic interface with hysteresis and particle reuse.
- Gate 3: conservative two-way coupling.

See [docs/GATES.md](docs/GATES.md), [docs/GATE1A.md](docs/GATE1A.md), and
[docs/GATE1B.md](docs/GATE1B.md).

## Reproducibility

- MUI is pinned to commit `b130c7a12aa8e7ac8d54e9188c4836342daed263`.
- Gate 1B refuses to run without the Gate 1A PASS artifact.
- Cases are copied into a unique, non-overwriting run directory.
- No flat-plate or production DSMC job is submitted by this branch.

## License

GPL-3.0-or-later. MUI retains its upstream dual Apache-2.0/GPL-3.0 licensing.
