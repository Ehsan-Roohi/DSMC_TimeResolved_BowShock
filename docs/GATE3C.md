# Gate 3C: physical cylinder preflight

The moving-interface Gate 3B pilot passed on Unity before this physical case
was defined. Gate 3C now replaces the manufactured arc fluxes with actual
OpenFOAM-v2312 continuum fields and a real DSMC cylinder cloud. It is the
physical preflight immediately before applying the conservative DSMC flux to
the continuum solver and measuring parallel scaling.

## Predeclared case

- monatomic argon at `n_inf = 1e20 m^-3` and `T_inf = 300 K`;
- stream velocity `1500 m/s` (approximately Mach 4.65);
- cylinder radius `0.01 m`, diffuse Maxwellian wall at `550 K`;
- body-fitted annular outer radius `0.05 m`, span `0.0025 m`;
- continuum mesh: 32 radial by 64 angular by one spanwise cell;
- full-DSMC reference: 16 radial by 64 angular by one cell;
- hybrid DSMC region: cylinder to the independently fixed radius `0.025 m`,
  six radial by 64 angular cells; and
- DSMC: 1600 steps of `2.5e-7 s`, sampling every fifth step from 600 through
  1600.

All three cases use the same 64-face cylinder surface. The continuum solution
is completed first and sampled just outside the fixed interface. MUI then
supplies number density, all velocity components, and temperature to the real
DSMC reservoir on the circular interface. Only after the hybrid calculation
is complete is the full-domain DSMC reference run.

## Acceptance

The 201 post-transient observations on every cylinder face are divided into
four contiguous blocks. Heat-flux and streamwise force-density profiles are
compared with the full-DSMC block-mean 95% intervals. Each profile passes when
its normalized L2 error is no larger than the greater of 5% or the normalized
reference uncertainty.

This gate is intentionally labeled a physical preflight. A PASS proves the
body-fitted cylinder mesh, continuum-to-DSMC reservoir, wall statistics, and
reference ordering. It does **not** claim that DSMC flux has already been
applied back to the continuum solver, that the physical interface has moved,
or that parallel scaling is complete. Those claims remain machine-readable
`false` in the Gate 3C summary and are the acceptance items of the next gate.

## Unity result

Gate 3C passed in Unity job `63661524` with exit code `0:0`. The heat-flux
normalized L2 error was `0.121561` against an uncertainty-based threshold of
`0.198717`; drag-density error was `0.0846554` against `0.161688`; and total
drag differed by `1.8287%`. Publisher, hybrid DSMC, and full-DSMC reference all
completed 1600 steps. The immutable result is
[`results/gate3c_physical_unity_63661524.json`](results/gate3c_physical_unity_63661524.json).
