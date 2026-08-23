# Gate 3A: conservative flux-transfer and restart gate

Gate 3 is split before the cylinder production case. Gate 3A isolates the
conservative numerical contract from OpenFOAM solver physics and DSMC
sampling cost. Gate 3B will embed the accepted contract into the adaptive
`rhoCentralFoamMUI`/`dsmcFoamMUI` cylinder calculation.

## Contract

The DSMC-side MPMD application publishes block-integrated mass, three
momentum components, and total-energy fluxes on a 3-by-3 source layout. The
continuum-side application maps them to a 4-by-4 face layout with MUI's
conservative RBF sampler. Integrated fluxes are mapped before division by
continuum face area; therefore the sum, rather than a point value, is the
conserved quantity.

Each flux window also carries a sample count and maximum relative standard
error. Relaxation is forbidden unless the window contains at least 64
samples and its maximum relative standard error is at most 0.05. The
controlled three-window sequence contains:

- one unresolved 32-sample window that must be skipped;
- one resolved 256-sample window relaxed with alpha 0.35; and
- one resolved 512-sample window relaxed with alpha 0.50.

Both the raw conservative mapping and the relaxed global balance must agree
with their DSMC-side totals within `1e-8` relative.

## Restart audit

The same three windows are executed twice:

1. continuously as windows 0, 1, and 2; and
2. as a fresh windows 0-1 segment followed by a restarted window-2 segment.

The restart is written atomically, validates its schema, face count, window
number, finiteness, completeness, and absence of trailing data. The final
continuous and restarted flux states must be byte-for-byte identical.

## Scope boundary

Gate 3A proves the MUI transport, conservative RBF operator, statistical
relaxation guard, global flux audit, and restart determinism. It deliberately
does not claim cylinder validation or parallel scaling; those are Gate 3B
acceptance items after this smaller gate passes on Unity.
