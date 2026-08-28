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

Unity status: passed in job `63661524`. Heat-flux normalized L2 error was
`0.12156` against `0.19872`; drag-density error was `0.08466` against
`0.16169`; and total-drag relative error was `0.01829`. The immutable record is
[`docs/results/gate3c_physical_unity_63661524.json`](results/gate3c_physical_unity_63661524.json).

## Gate 3D - physical feedback replay and scaling

- use the actual Gate 3C hybrid DSMC heat and force statistics as the physical
  reverse-feedback source;
- transport five integrated conservative components through MUI;
- apply the equal-and-opposite relaxed packet to real OpenFOAM-v2312 `p/U/T`
  fields with one global positivity-preserving scale;
- move each angular transfer location by a bounded physical discrepancy
  indicator and preserve exact checkpoint/restart state;
- verify conservation through mapping, relaxation, and field application; and
- audit the deterministic coupling kernel on one, two, and four MPI ranks.

Gate 3D is explicitly a replay of completed physical DSMC statistics. Its
summary keeps `live_concurrent_openfoam_dsmc_completed=false`. A PASS
authorizes Gate 3E, where the OpenFOAM and DSMC solvers run concurrently while
the physical interface evolves. See [`docs/GATE3D.md`](GATE3D.md).

Unity status: passed in job `63673123`. All five core tests passed, the
OpenFOAM feedback application conserved the globally scaled reaction to
`8.2718e-25`, restart was byte-identical, and the 1/2/4-rank checksums agreed
to `3.3881e-21`.

## Gate 3E - live concurrent solver coupling

- resume the actual Gate 3C continuum and DSMC physical states;
- keep derived `rhoCentralFoam` and `dsmcFoam` alive concurrently in one MPMD
  execution;
- exchange live continuum reservoir states at every synchronized step;
- sample and return actual DSMC wall force and heat flux in five windows;
- apply the conservative, positivity-limited reaction inside the continuing
  continuum solve; and
- move and audit the continuum sampling surface without claiming dynamic DSMC
  repartitioning.

Gate 3E requires the immutable Gate 3D PASS artifact. Its exact scope and
acceptance criteria are documented in [`docs/GATE3E.md`](GATE3E.md).

Unity status: passed in job `63696880`. Both real solvers completed 1000
synchronized steps and five 40-sample windows, the feedback-application
conservation error was `1.55096e-25`, maximum velocity and temperature changes
were `4.18249 m/s` and `5.57070 K`, and both applications observed exactly 112
adaptive layer changes. The immutable record is
[`docs/results/gate3e_unity_63696880.json`](results/gate3e_unity_63696880.json).

## Gate 3F - live dynamic DSMC particle ownership

- move an internal DSMC particle-ownership boundary with the live MUI layer
  request while retaining the validated Gate 3C mesh topology;
- preserve every retained particle `(origProc, origId)` across transitions;
- seed newly activated cells with moment-exact six-particle packets;
- remove all particles from inactive cells and require zero inactive inventory;
- require activation mismatch within one DSMC sampling standard error; and
- close an exact parcel ledger at every live step while retaining Gate 3E's
  physical two-way feedback and continuum conservation acceptance.

Gate 3F requires the immutable Gate 3E PASS artifact. See
[`docs/GATE3F.md`](GATE3F.md).

Unity status: passed in job `63702483`. Both live solvers completed 1000
synchronized steps, the dynamic particle ledger and inactive-particle count
were exactly zero, and 7,091,281 retained identities were audited. The
immutable record is
[`docs/results/gate3f_unity_63702483.json`](results/gate3f_unity_63702483.json).

## Gate 3G - live coupled checkpoint/restart

- compare a 1000-step continuous live calculation with a 600+400-step
  checkpoint/restart calculation;
- preserve the 64 dynamic layer requests and fractional reservoir state;
- prove that restart continues at step 601 without a duplicated or missing
  coupling step;
- require exact particle ownership before and after restart;
- compare stochastic DSMC observables inside declared sampling tolerances; and
- audit the dynamic ownership/checkpoint kernel on one, two, and four MPI
  ranks without claiming full-solver domain-decomposition scaling.

Gate 3G requires the immutable Gate 3F PASS artifact. See
[`docs/GATE3G.md`](GATE3G.md).
