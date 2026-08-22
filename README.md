# OpenFOAM MUI DSMC-NS Coupling

This repository modernizes the one-way hybrid `rhoCentralFoam`/`dsmcFoam`
method described by Darbandi and Roohi (*International Journal for Numerical
Methods in Fluids*, 2013, DOI: `10.1002/fld.3769`).

Development is gated. A later physical or production case is never submitted
until the smaller API, transport, conservation, and equilibrium checks pass.

## Current branch: Gate 1A

Gate 0 passed on Unity with OpenFOAM-v2312, OpenMPI 4.1.6, and pinned MUI-v2.
Gate 1A now verifies the exact fixed-interface contracts needed by Gate 1B:

1. the OpenFOAM continuum boundary-field API can publish face centres and
   `rho`, `Ux`, `Uy`, `Uz`, and `T`;
2. the installed v2312 DSMC API exposes `dsmcCloud::addNewParcel` to the
   receiver adapter;
3. the five fields cross a three-dimensional MUI interface at twelve fixed
   face centres; and
4. moment-exact Maxwellian particle packets reproduce mass, momentum, and
   energy within `1e-12` relative error.

This subgate does not run a physical flat plate and does not claim validation
of wall heat flux or shear.

## Unity one-line submission

```bash
ROOT=/project/pi_roohie_umass_edu/github_sync/OpenFOAM-MUI-DSMC-NS; cd "$ROOT" && git fetch origin mui-dsmc-ns-gate1a && git checkout mui-dsmc-ns-gate1a && git pull --ff-only origin mui-dsmc-ns-gate1a && OPENFOAM_MODULE=openfoam/2312 bash scripts/submit_unity_gate1a.sh
```

The command requires the Gate 0 PASS artifacts in the same checkout. It prints
the Slurm job ID and exact log path. Gate 1A is expected to finish within a few
minutes.

## Gate sequence

- Gate 0: environment, MPI ABI, and MUI MPMD transport — passed on Unity.
- Gate 1A: v2312 adapter API plus fixed-interface equilibrium audit — current.
- Gate 1B: short uniform-equilibrium run with the actual two solvers.
- Gate 1C: flat-plate comparison against full DSMC uncertainty.
- Gate 2: automatic interface with hysteresis and particle reuse.
- Gate 3: conservative two-way coupling.

See [docs/GATES.md](docs/GATES.md) and [docs/GATE1A.md](docs/GATE1A.md).

## Reproducibility

- MUI is pinned to commit `b130c7a12aa8e7ac8d54e9188c4836342daed263`.
- Gate 1A refuses to run without the Gate 0 PASS artifact.
- No production DSMC job is submitted by this branch.

## License

GPL-3.0-or-later. MUI retains its upstream dual Apache-2.0/GPL-3.0 licensing.
