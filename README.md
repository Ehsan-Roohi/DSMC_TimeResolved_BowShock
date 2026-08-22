# OpenFOAM MUI DSMC-NS Coupling

This repository is the gated modernization of the one-way hybrid
`rhoCentralFoam`/`dsmcFoam` method described by Darbandi and Roohi
(*International Journal for Numerical Methods in Fluids*, 2013,
DOI: `10.1002/fld.3769`).

The implementation is deliberately gated. No DSMC production case should be
submitted until the installed OpenFOAM distribution, solver sources, MPI ABI,
and MUI MPMD transport have passed Gate 0.

## Current branch: Gate 0

Gate 0 performs two checks:

1. records the exact OpenFOAM/MPI/compiler installation visible in the Unity
   batch environment; and
2. compiles a pinned MUI-v2 smoke program and transfers five continuum state
   fields (`rho`, `Ux`, `Uy`, `Uz`, and `T`) between two MPMD applications.

It does **not** run a physical DSMC case. Its output determines the exact
OpenFOAM adapter required for Gate 1 without guessing the OpenFOAM API or MPI
communicator layout.

## Unity one-line submission

```bash
ROOT=/project/pi_roohie_umass_edu/github_sync/OpenFOAM-MUI-DSMC-NS; if [ ! -d "$ROOT/.git" ]; then git clone --branch mui-dsmc-ns-gate0 --single-branch https://github.com/Ehsan-Roohi/DSMC_TimeResolved_BowShock.git "$ROOT"; fi; cd "$ROOT" && git fetch origin mui-dsmc-ns-gate0 && git checkout mui-dsmc-ns-gate0 && git pull --ff-only origin mui-dsmc-ns-gate0 && bash scripts/submit_unity_gate0.sh
```

The command prints the Slurm job ID and the exact log path. Gate 0 is expected
to finish in less than ten minutes. The first build can take longer if MUI has
not yet been cached.

## Local execution

```bash
bash scripts/run_gate0.sh
```

## Gate policy

See [docs/GATES.md](docs/GATES.md). Gate 1 will add a one-way
`rhoCentralFoam -> dsmcFoam` interface only after Gate 0 identifies the actual
Unity OpenFOAM family and version.

## Reproducibility

- MUI is pinned to commit `b130c7a12aa8e7ac8d54e9188c4836342daed263`.
- The probe records `WM_PROJECT`, `WM_PROJECT_VERSION`, solver executable and
  source locations, MPI implementation, compiler versions, and Slurm context.
- No long run is submitted by this branch.

## License

GPL-3.0-or-later. MUI is fetched from its upstream repository and retains its
upstream dual Apache-2.0/GPL-3.0 licensing.
