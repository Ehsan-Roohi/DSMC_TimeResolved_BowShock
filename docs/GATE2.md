# Gate 2: automatic interface and particle reuse

Gate 2 isolates adaptive domain decomposition from the conservative two-way
flux coupling reserved for Gate 3. It uses real OpenFOAM-v2312 continuum
fields and a real `dsmcCloud`; it does not use a full-DSMC or experimental
solution to place the interface.

## Breakdown indicator

The continuum flat-plate case from Gate 1C is written at five physical times.
For every continuum cell the utility evaluates the maximum of three
gradient-length local Knudsen numbers,

`max(lambda |grad(n)|/n, lambda |grad(T)|/T,
lambda |grad(U)|/max(|U|, sqrt(2 k T/m)))`.

Values from each 2-by-2 continuum-cell block are reduced onto the 40-by-20
kinetic grid. The activation threshold is `0.05`, a commonly used conservative
continuum-breakdown cutoff. Deactivation uses `0.03`, so fluctuations inside
the gap cannot chatter the interface. Each streamwise column remains
wall-connected, includes at least one kinetic layer, and receives one halo
layer above the highest selected cell.

## Controlled transient replay

The five actual continuum snapshots are replayed forward and then backward,
without duplicating the final snapshot. The resulting nine frames must
exercise all three lifecycle paths:

- an inactive cell crosses `0.05` and is activated;
- a retained cell remains above `0.03`; and
- a previously active cell falls below `0.03` and is deactivated.

The reverse replay is an algorithmic hysteresis test. It is not presented as
a time-reversible physical solution.

## Real parcel lifecycle audit

`gate2ParticleManager` constructs and edits the v2312 `dsmcCloud` directly.
For each transition it records every retained parcel's `(origProc, origId)`,
deletes parcels only from deactivated cells, and creates moment-exact
six-particle packets only in newly activated cells. The retained identity sets
must be identical before and after the transition, and no inactive cell may
contain a parcel.

Newly activated cells are initialized from their continuum number density,
velocity, and temperature. Density, velocity, and temperature mismatches are
normalized by their finite-particle sampling standard errors; their maximum
must not exceed one standard error. This checks activation handoff quality,
not the statistically evolved two-way overlap that belongs to Gate 3.

The `0.05` gradient-length cutoff is consistent with published hybrid
DSMC/continuum practice; see the NASA continuum-breakdown discussion
[here](https://ntrs.nasa.gov/api/citations/20160010331/downloads/20160010331.pdf).

## Acceptance

Gate 2 passes only when:

1. all nine 800-cell indicator frames are finite and physical;
2. activation, retention, and deactivation all occur;
3. retained parcel identities are unchanged;
4. parcel creation occurs if and only if cells are newly activated;
5. inactive cells contain no parcels;
6. the activation mismatch is at most one sampling standard error; and
7. the analyzer confirms that no external reference positioned the interface.
