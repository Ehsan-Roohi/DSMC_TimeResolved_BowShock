# Gate 3M: long multi-window stability

Gate 3M runs the real coupled `rhoCentralFoam` and `dsmcFoam` executables for
10,000 coupled steps (50 coupling windows) on the Gate 3L-selected `2+2` MPI
layout.  It is a duration and state-persistence gate, not another proxy or
short scaling benchmark.

PASS requires complete time advancement by both solvers, two-way feedback,
finite nonzero wall flux, persistent adaptive DSMC layers, zero ownership
imbalance, zero inactive parcels, global wall-flux reduction, unique interface
ownership, a written checkpoint, and feedback conservation error below
`1e-12`.
