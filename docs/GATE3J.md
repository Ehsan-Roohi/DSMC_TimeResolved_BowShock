# Gate 3J: live spatially distributed coupling

Gate 3J advances the actual derived OpenFOAM-v2312 `rhoCentralFoam` and
`dsmcFoam` solvers concurrently after decomposing both complete cases into two
Cartesian x-slabs. The four-rank MPMD job uses separate OpenFOAM sub-worlds and
a distributed MUI application domain for each solver.

## PASS criteria

- Gate 3I is a verified PASS.
- Both full-field decompositions pass parallel `checkMesh`.
- Exactly one continuum rank owns every one of the 64 sampling points.
- Exactly one DSMC rank owns every angular/radial kinetic cell.
- Global wall heat and force samples are reduced before MUI feedback.
- Both real solvers advance 200 synchronized physical steps and one complete
  coupling window on two spatial ranks each.
- The continuum applies nonzero two-way feedback with conservation error at or
  below `1e-12`.
- The global DSMC parcel ledger closes exactly and no inactive parcel remains.

## Scope boundary

This gate proves one live spatially decomposed physical coupling window. It
does not yet claim distributed checkpoint/restart equivalence or spatial
strong scaling; those are deferred until this first distributed run passes.
