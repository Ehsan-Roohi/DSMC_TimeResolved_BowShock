# Gate 1C: fixed-interface flat-plate physical validation

Gate 1C is the first non-uniform physical gate. It follows the one-way,
state-based coupling direction used in the motivating flat-plate work, while
using MUI for the actual spatial boundary-state handoff. It does not claim the
two-way conservative flux coupling reserved for Gate 3.

## Predeclared case

- gas: monatomic argon, `n_inf = 1e20 m^-3`, `T_inf = 300 K`;
- stream velocity: `1500 m/s` (approximately Mach 4.65);
- plate: `0.1 m` long, diffuse Maxwellian wall at `550 K`;
- full domain: `0.1 x 0.05 x 0.0025 m`, 40 x 20 x 1 DSMC cells;
- near-wall DSMC domain: `0.1 x 0.015 x 0.0025 m`, 40 x 6 x 1 cells;
- fixed interface: `y = 0.015 m` plus the kinetic inlet and outlet;
- DSMC: 1600 steps of `2.5e-7 s`, VHS argon and `4e10` real molecules per
  parcel; and
- sampling: every fifth step from step 600 through 1600.

The continuum case uses 80 x 40 x 1 cells, ideal-gas argon, constant
`mu = 2.23e-5 Pa s`, `Pr = 2/3`, and laminar `rhoCentralFoam`.

## Evidence ordering

The runner enforces this order:

1. solve the continuum flat-plate case;
2. read the latest continuum snapshot and publish number density, all three
   velocity components, and temperature at 52 fixed kinetic boundary face
   centres;
3. run the near-wall DSMC solver with a live MUI reservoir; and
4. only after the hybrid run has finished, run the full-domain DSMC reference.

The ordering is deliberate. Neither the full-DSMC result nor its wall data can
move the interface or modify the hybrid reservoir.

The custom kinetic solver applies the mapped state, not merely an audit copy.
For every open boundary face it evaluates the Bird half-range Maxwellian flux,
keeps fractional-parcel carry-over, samples inward velocities, and inserts
real v2312 `dsmcCloud` parcels. The reference uses the stock v2312
`FreeStream` inflow model. Both collect the native `q` and `fD` wall fields
after each sampled DSMC step.

## Statistical acceptance

For each of 40 plate faces, the post-transient samples are split into four
contiguous blocks. The analyzer forms a Student-t 95% interval from the four
full-DSMC block means. It then computes profile-level normalized L2 errors for
heat flux and streamwise shear.

For each observable, the acceptance threshold is

`max(0.03, normalized L2 norm of the full-DSMC 95% half-width)`.

Gate 1C passes only if both heat flux and shear errors are at or below their
own thresholds. The summary records the raw error, uncertainty contribution,
threshold, and Boolean result; a failed comparison remains a valid physical
result and is not relabelled as a pass.

The case construction follows the OpenFOAM-v2312 DSMC field and inflow
contracts. The upstream DSMC flat-plate/wedge tutorial is available in the
[OpenFOAM source mirror](https://github.com/sajjadimhd/OpenFOAMv2312/tree/main/tutorials/discreteMethods/dsmcFoam/wedge15Ma5),
and the motivating method is documented at
[DOI 10.1002/fld.3769](https://onlinelibrary.wiley.com/doi/abs/10.1002/fld.3769).
