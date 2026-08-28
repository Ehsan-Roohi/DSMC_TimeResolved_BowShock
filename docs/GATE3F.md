# Gate 3F: live dynamic DSMC particle ownership

Gate 3E passed in Unity job `63696880`: the real derived OpenFOAM-v2312
`rhoCentralFoam` and `dsmcFoam` advanced concurrently for 1000 synchronized
steps and five physical feedback windows. Gate 3F closes the one scope flag
that Gate 3E intentionally left false: dynamic DSMC particle ownership.

## Dynamic ownership boundary

The validated Gate 3C six-layer annular DSMC mesh is retained. Gate 3F does
not alter mesh topology. Instead, each angular column has a moving internal
particle-ownership boundary driven by the same four-to-eight continuum-layer
request transported through MUI. Because the DSMC radial spacing is twice the
continuum spacing, requests snap outward to two, three, or four active DSMC
layers. Reservoir particles are injected through that internal cylindrical
surface rather than the fixed outer patch.

For every transition the live DSMC solver:

- preserves `(origProc, origId)` for every particle in retained cells;
- deletes particles in deactivated or otherwise inactive cells;
- initializes newly activated cells with moment-exact six-particle packets;
- requires activation density, velocity, and temperature to remain within one
  finite-particle sampling standard error; and
- checks at every step that
  `final = initial + reservoir-injected + transition-seeded - removed`.

Particles that stream beyond the current internal boundary are removed before
the next exchange. No inactive cell may contain a particle.

## Acceptance

Gate 3F passes only if:

- both real solvers again complete exactly 1000 synchronized steps and five
  40-sample feedback windows;
- MUI uses the distinct `mpi://continuum/gate3f` and `mpi://dsmc/gate3f`
  applications;
- activation, deactivation, seeding, removal, and retained-identity paths all
  occur during the live run;
- the maximum inactive-particle count and ownership-ledger error are zero;
- activation mismatch is at most one DSMC sampling standard error; and
- physical wall feedback remains nonzero and its continuum application
  conserves the globally scaled packet within `1e-12`.

A PASS sets `adaptive_particle_domain_completed=true` while explicitly
recording `mesh_topology_changed=false`.

## Unity result

Gate 3F passed in job `63702483` with exit code `0:0`. The maximum inactive
parcel count and ownership balance error were zero, 7,091,281 retained
particle identities were audited, and the feedback-application conservation
error was `1.654361e-24`. The immutable record is
[`results/gate3f_unity_63702483.json`](results/gate3f_unity_63702483.json).
