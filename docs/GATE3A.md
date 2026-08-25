# Gate 3A: conservative flux-transfer and restart gate

Gate 3 is split before the cylinder production case. Gate 3A isolates the
conservative numerical contract from OpenFOAM solver physics and DSMC
sampling cost. Gate 3B will embed the accepted contract into the adaptive
`rhoCentralFoamMUI`/`dsmcFoamMUI` cylinder calculation.

## Contract

The DSMC-side MPMD application publishes block-integrated mass, three
momentum components, and total-energy fluxes on a 3-by-3 source layout. The
continuum-side application maps them to a 4-by-4 face layout with MUI's
conservative RBF sampler. The pinned MUI-v2 operator is followed by an
area-weighted projection that removes only its global constant-mode residual.
The unprojected RBF defect must remain below `0.05`; therefore the projection
cannot conceal a failed or grossly inaccurate mapping. Integrated fluxes are
mapped before division by continuum face area, so their sum is conserved.

Each flux window also carries a sample count and maximum relative standard
error. Relaxation is forbidden unless the window contains at least 64
samples and its maximum relative standard error is at most 0.05. The
controlled three-window sequence contains:

- one unresolved 32-sample window that must be skipped;
- one resolved 256-sample window relaxed with alpha 0.35; and
- one resolved 512-sample window relaxed with alpha 0.50.

Both the projected mapping and the relaxed global balance must agree with
their DSMC-side totals within `1e-8` relative. The raw RBF defect is recorded
separately in the machine-readable summary.

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

## Unity result

Gate 3A passed in Unity job `63589917` with exit code `0:0`. The maximum raw
RBF defect was `0.0170238` against the predeclared `0.05` limit. The projected
global error was exactly zero and the maximum relaxed error was `2.41214e-16`
against a `1e-8` tolerance. The restarted result matched the continuous state
byte for byte. The immutable record is
[`results/gate3a_unity_63589917.json`](results/gate3a_unity_63589917.json).
