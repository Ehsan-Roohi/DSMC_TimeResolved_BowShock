# Gate 3H: full-solver MPMD ensemble scaling

Gate 3G passed in Unity job `63737420`. Gate 3H replaces the short synthetic
kernel benchmark with complete live `rhoCentralFoam`/`dsmcFoam` pairs. It
measures throughput for one, two, and four independent coupled replicas using
2, 4, and 8 MPI ranks on one allocated node.

Each replica advances both real derived OpenFOAM-v2312 solvers for 400
synchronized steps and two physical feedback windows. Every pair has an
independent MUI domain/session, case directory, DSMC cloud, dynamic ownership
ledger, and coupling checkpoint.

## Acceptance

Gate 3H passes only if:

- all seven full-solver replicas complete both applications;
- every replica advances steps 1 through 400 and closes two windows;
- two-way feedback is applied with conservation error at most `1e-12`;
- every DSMC replica has zero inactive parcels and zero ownership imbalance;
- physical flux and final parcel population remain inside the Gate 3G sampling
  tolerances; and
- measured wall time, throughput speedup, and efficiency are recorded for
  1, 2, and 4 coupled replicas.

This is full-solver **ensemble throughput scaling**. It is not spatial domain
decomposition of a single coupled cylinder, and the machine-readable summary
therefore records `domain_decomposition_completed=false`. A later gate can add
strong scaling without inflating this result's scope.
