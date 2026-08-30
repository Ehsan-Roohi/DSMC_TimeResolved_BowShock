# Gate 3K: distributed checkpoint/restart equivalence

Gate 3K extends the verified Gate 3J live 2+2-rank calculation across a real
checkpoint/restart boundary. It compares a continuous 400-step run against a
split run that advances steps 1-200, stops both OpenFOAM applications, and then
restarts at step 201 through step 400.

The split point is a complete 200-step coupling-window boundary. Restarting in
the middle of a window would intentionally leave wall-sampling and feedback
accumulators incomplete and would not be a clean checkpoint test.

## State restored

- decomposed continuum fields in both processor directories;
- decomposed DSMC cloud and parcel identity metadata;
- all 64 adaptive layer requests;
- all 64 fractional reservoir accumulators; and
- the logical MUI coupling-step boundary.

## Acceptance

Every continuous, fresh, and restarted segment must run the real distributed
rhoCentralFoam and dsmcFoam solvers on two spatial ranks each. Step 200 must be
followed by step 201 without duplication or omission. Interface ownership,
global wall-flux reduction, particle ledger closure, inactive-parcel inventory,
feedback conservation, and checkpoint validation remain hard gates.

DSMC is stochastic, so particle clouds are not required to be byte-identical.
The post-restart wall-flux checksum and final global parcel population must
match the continuous run within declared finite-sampling tolerances. Gate 3K
does not yet claim spatial strong scaling; that is deferred to Gate 3L.
