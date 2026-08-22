# Development gates

## Gate 0 - environment and transport

Required before any OpenFOAM adapter is compiled:

- exact OpenFOAM family and version recorded;
- `rhoCentralFoam` and `dsmcFoam` executable and source trees located;
- compiler and MPI ABI recorded;
- pinned MUI builds with the same MPI wrapper; and
- two MPMD applications exchange `rho`, `U`, and `T` without mismatch.

Unity status: passed with OpenFOAM-v2312 and OpenMPI 4.1.6.

## Gate 1A - fixed-interface API and moment audit

- compile the continuum boundary-field publisher contract against v2312;
- compile and link the receiver contract through `dsmcCloud::addNewParcel`;
- transfer five state fields at fixed three-dimensional face centres;
- reject every non-finite or non-physical mapped state; and
- reproduce equilibrium mass, momentum, and energy within `1e-12` using a
  six-particle moment-exact Maxwellian quadrature.

No physical CFD/DSMC case is submitted in Gate 1A.

## Gate 1B - actual solver uniform equilibrium

- runtime continuum publisher inside `rhoCentralFoam`;
- MUI-driven reservoir inflow model inside `dsmcFoam`;
- identical fixed overlap geometry, gas model, and time synchronization;
- no DSMC-to-continuum feedback; and
- statistically stationary mass, momentum, and energy with no systematic
  interface drift.

## Gate 1C - flat-plate physical validation

- fixed interface independent of the full-DSMC result;
- wall heat flux and shear compared with full DSMC; and
- agreement inside the full DSMC 95% sampling interval or 3% normalized L2
  error, whichever is larger.

## Gate 2 - automatic interface

- combined continuum-breakdown indicator;
- activation/deactivation hysteresis;
- particle reuse in retained DSMC cells;
- particle creation only in newly activated cells;
- overlap mismatch normalized by DSMC sampling uncertainty; and
- no dependence on a full-DSMC or experimental solution to position the
  interface.

## Gate 3 - two-way conservative coupling

- block-averaged DSMC mass, momentum, and energy fluxes;
- conservative RBF transfer to the continuum mesh;
- relaxation applied only to statistically resolved flux windows;
- global conservation audit and restart consistency; and
- cylinder validation and parallel scaling study.
