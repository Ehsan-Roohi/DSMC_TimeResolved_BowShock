# Gate 1A: fixed-interface API and equilibrium audit

Gate 1A is the compile-and-transport subgate between environment qualification
and the first physical coupled case. It deliberately does not submit a flat
plate or any long DSMC calculation.

It requires all of the following:

- the Gate 0 PASS artifact from the same checkout;
- compilation against the installed OpenFOAM-v2312 boundary-field API;
- compilation and linking of `dsmcCloud::addNewParcel`;
- a three-dimensional MUI fixed-interface transfer of `rho`, `Ux`, `Uy`, `Uz`,
  and `T` at twelve interface face centres;
- finite and physical mapped states at all receiving points; and
- a moment-exact six-particle Maxwellian quadrature with relative mass,
  momentum, and energy error no larger than `1e-12`.

Passing Gate 1A authorizes Gate 1B: a short uniform-equilibrium run using the
actual `rhoCentralFoam` and `dsmcFoam` executables. It does not authorize the
flat-plate validation or a production DSMC run.
