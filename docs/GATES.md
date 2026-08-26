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

Unity status: passed in job `63484646` with 10 coupled steps, continuum
conservation error `6.31e-34`, DSMC conservation error `5.71e-16`, and
maximum cross-state error `8.96e-7`.

## Gate 1C - flat-plate physical validation

- fixed interface independent of the full-DSMC result;
- wall heat flux and shear compared with full DSMC; and
- agreement inside the full DSMC 95% sampling interval or 3% normalized L2
  error, whichever is larger.

Unity status: passed in resume job `63489859`. Heat-flux normalized L2 error
was `0.3115` against a `0.3882` sampling threshold; shear error was `0.2598`
against a `0.3602` threshold.

## Gate 2 - automatic interface

- combined continuum-breakdown indicator;
- activation/deactivation hysteresis;
- particle reuse in retained DSMC cells;
- particle creation only in newly activated cells;
- overlap mismatch normalized by DSMC sampling uncertainty; and
- no dependence on a full-DSMC or experimental solution to position the
  interface.

Unity status: passed in job `63533453` across nine forward/reverse frames.
There were 717 dynamic activations and 717 deactivations, retained particle
identities were preserved, and the maximum activation mismatch was `0.4874`
sampling standard deviations against an allowed value of 1.0. The record is
[`docs/results/gate2_unity_63533453.json`](results/gate2_unity_63533453.json).

## Gate 3A - conservative flux contract

- MUI MPMD transport of block-integrated mass, momentum, and energy fluxes;
- conservative RBF transfer to a different continuum face layout with a
  bounded raw defect and area-weighted global projection;
- relaxation only for statistically resolved flux windows;
- global projected and relaxed conservation within `1e-8`; and
- byte-identical continuous and checkpoint/restart results.

Unity status: passed in job `63589917`. The raw RBF defect was `0.0170238`,
the projected error was zero, the relaxed error was `2.41214e-16`, and the
restart matched the continuous state byte for byte. See
[`docs/GATE3A.md`](GATE3A.md).

## Gate 3B - coupled cylinder and scaling

- embed the Gate 3A flux contract in the real adaptive solvers;
- audit global conservation during interface motion;
- validate the cylinder against full DSMC uncertainty; and
- complete the parallel scaling study.

Gate 3B is not submitted until Gate 3A passes.

The first Gate 3B submission is a moving-cylinder integration pilot across
three nonmatching interface resolutions. It closes moving-boundary and restart
risk before the full OpenFOAM cylinder validation and parallel scaling run.
The pilot is documented in [`docs/GATE3B.md`](GATE3B.md) and cannot itself be
reported as completion of the final physical Gate 3B.

Unity status: the pilot passed in job `63628509`. Maximum raw RBF error was
`8.01848e-7`, maximum moving-boundary conservation error was `6.27783e-16`,
and restart was byte-identical.

## Gate 3C - physical cylinder preflight

- body-fitted Mach-4.65 argon cylinder in real OpenFOAM-v2312 solvers;
- MUI continuum-to-DSMC circular reservoir at a predeclared radius;
- cylinder heat flux and drag compared with full-DSMC block uncertainty; and
- evidence ordering that prevents the reference from selecting the interface.

Gate 3C deliberately keeps two-way application, adaptive physical interface
motion, and parallel scaling false in its summary. A PASS authorizes that final
coupled/scaling gate. See [`docs/GATE3C.md`](GATE3C.md).
