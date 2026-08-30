# Gate 3I: spatial-decomposition preflight

Gate 3I closes the infrastructure gap identified explicitly by Gate 3H. It
decomposes the actual Gate 3H continuum and hybrid DSMC meshes with OpenFOAM
`decomposePar -no-fields`, validates both decomposed meshes with parallel
`checkMesh -constant`, and
exercises bidirectional MUI transport with 1+1, 2+2, and 4+4 MPI ranks.
The decomposition uses OpenFOAM's built-in `simple` method with `(N 1 1)`
Cartesian x-slabs so the gate does not depend on an optional Scotch library.

## PASS criteria

- Gate 3H is a verified PASS.
- Both OpenFOAM cases pass serial and 2/4-rank mesh validation.
- The processor-directory inventory exactly matches the requested ranks.
- Every rank in both MUI application domains sends and receives its own value.
- The analyzer sees exactly 2, 4, and 8 total MPI ranks.

## Scope boundary

This gate validates spatial decomposition and multi-rank transport plumbing. It
intentionally does not decompose transient fields or advance the two decomposed
physical solvers and therefore records
`live_distributed_openfoam_dsmc_completed=false`. A PASS authorizes Gate 3J,
which adds distributed ownership/reduction logic to the live solvers.
