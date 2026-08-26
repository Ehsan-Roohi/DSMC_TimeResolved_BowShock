# Gate 3B pilot: moving cylindrical interface

Gate 3A passed the fixed-layout conservative transfer and deterministic
restart gate. The first Gate 3B submission is deliberately a bounded
integration pilot before an expensive full-cylinder calculation. It exercises
the accepted flux contract on a moving semicylindrical interface and three
nonmatching source/target resolutions.

## Pilot contract

- MUI MPMD transfers block-integrated mass, three momentum components, and
  total-energy fluxes from a DSMC-side arc to a different continuum arc.
- Five windows contract and expand the interface while a one-layer-per-window
  limiter exercises both activation and deactivation.
- The first window is statistically unresolved and must not be relaxed.
- The raw conservative-RBF defect is recorded and bounded by `0.2`; the
  area-weighted projection, relaxed balance, and moving-boundary balance must
  each remain within `1e-8`.
- Coarse, medium, and fine nonmatching layouts use 12/16, 18/24, and 24/32
  DSMC/continuum faces.
- A medium-resolution checkpoint/restart must reproduce the continuous final
  state byte for byte.

The runner refuses to submit unless the machine-readable Gate 3A result proves
MUI transport, bounded raw RBF error, projected and relaxed conservation,
unresolved-window rejection, and byte-identical restart.

## Scope boundary

This pilot is an integration-risk gate, not the final physical Gate 3B claim.
Its summary explicitly records that full DSMC cylinder validation and parallel
scaling are still incomplete. A pilot PASS authorizes embedding the moving
interface into the real OpenFOAM cylinder solvers; it does not substitute a
manufactured flux field for that physical evidence.

## Unity result

The pilot passed in Unity job `63628509` with exit code `0:0`. All four C++
tests passed. Across the coarse, medium, and fine nonmatching layouts, the
maximum raw RBF defect was `8.01848e-7`; the maximum projected, relaxed, and
moving-boundary conservation errors were `1.47096e-16`, `6.27783e-16`, and
`6.27783e-16`, respectively, against a `1e-8` tolerance. Six activation and
six deactivation events were exercised, and restart reproduced the continuous
medium result byte for byte. The immutable record is
[`results/gate3b_pilot_unity_63628509.json`](results/gate3b_pilot_unity_63628509.json).
