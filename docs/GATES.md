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

Unity status: passed with zero transfer error and `2.86e-16` maximum relative
moment error.

## Gate 1B - actual solver uniform equilibrium

- run derived, real v2312 `rhoCentralFoamMUI` and `dsmcFoamMUI` executables;
- hand continuum density, velocity and temperature to a real DSMC cloud;
- construct six moment-exact DSMC parcels in every periodic cell;
- exchange continuum and DSMC states at every physical time step;
- conserve mass, momentum and energy to `1e-10` relative in each solver; and
- keep cross-solver macrostate mismatch below `1e-3` relative.

This is a numerical integration gate, not a physical validation case.

Unity status: passed in job `63484646` with 10 coupled steps, continuum
conservation error `6.31e-34`, DSMC conservation error `5.71e-16`, and
maximum cross-state error `8.96e-7`.  The machine-readable record is
[`docs/results/gate1b_unity_63484646.json`](results/gate1b_unity_63484646.json).

## Gate 1C - flat-plate physical validation

- fixed interface independent of the full-DSMC result;
- wall heat flux and shear compared with full DSMC; and
- agreement inside the full DSMC 95% sampling interval or 3% normalized L2
  error, whichever is larger.

Unity status: passed in resume job `63489859` after the continuum and hybrid
phases from job `63489379`. Heat-flux normalized L2 error was `0.3115` against
a `0.3882` reference sampling threshold; shear error was `0.2598` against a
`0.3602` threshold. The machine-readable record is
[`docs/results/gate1c_unity_63489859.json`](results/gate1c_unity_63489859.json).

## Gate 2 - automatic interface

- combined continuum-breakdown indicator;
- activation/deactivation hysteresis;
- particle reuse in retained DSMC cells;
- particle creation only in newly activated cells;
- overlap mismatch normalized by DSMC sampling uncertainty; and
- no dependence on a full-DSMC or experimental solution to position the
  interface.

Implementation status: ready for Unity validation on branch
`mui-dsmc-ns-gate2`. Five real continuum snapshots are replayed forward and
backward to exercise both hysteresis transitions. A real v2312 `dsmcCloud`
audits retained `(origProc, origId)` identities, creation only in newly
activated cells, removal from deactivated cells, and sampling-normalized
activation mismatch. See [`docs/GATE2.md`](GATE2.md).

## Gate 3 - two-way conservative coupling

- block-averaged DSMC mass, momentum, and energy fluxes;
- conservative RBF transfer to the continuum mesh;
- relaxation applied only to statistically resolved flux windows;
- global conservation audit and restart consistency; and
- cylinder validation and parallel scaling study.
