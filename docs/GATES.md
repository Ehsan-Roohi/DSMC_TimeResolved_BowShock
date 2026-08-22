# Development gates

## Gate 0 - environment and transport

Required before any OpenFOAM adapter is compiled:

- exact OpenFOAM family and version recorded;
- `rhoCentralFoam` or its installed successor located;
- `dsmcFoam` executable and source located;
- compiler and MPI ABI recorded;
- pinned MUI builds with the same MPI wrapper;
- two MPMD applications exchange `rho`, `U`, and `T` without mismatch.

Pass artifact: `reports/gate0_summary.json` with `"status": "PASS"` and
`reports/unity_preflight.txt` containing the installed solver/source paths.

## Gate 1 - one-way fixed interface

Target: reproduce the 2013 method without manual data transfer.

- continuum sender publishes face centres, `rho`, `U`, and `T`;
- DSMC reservoir receives the fields and creates Maxwellian particles;
- the first implementation uses a fixed overlap boundary;
- no DSMC-to-continuum feedback;
- no long production run.

Pass criteria:

- uniform-equilibrium transfer has no drift in mass, momentum, or energy;
- mapped states are finite and physical at every receiving point;
- flat-plate wall heat flux and shear agree with full DSMC within the full
  DSMC 95% sampling interval or 3% normalized L2 error, whichever is larger.

## Gate 2 - automatic interface

- combined continuum-breakdown indicator;
- activation/deactivation hysteresis;
- particle reuse in retained DSMC cells;
- particle creation only in newly activated cells;
- overlap mismatch normalized by DSMC sampling uncertainty;
- no dependence on a full-DSMC or experimental solution to position the
  interface.

## Gate 3 - two-way conservative coupling

- block-averaged DSMC mass, momentum, and energy fluxes;
- conservative RBF transfer to the continuum mesh;
- relaxation applied only to statistically resolved flux windows;
- global conservation audit and restart consistency;
- cylinder validation and parallel scaling study.
