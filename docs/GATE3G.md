# Gate 3G: live coupled checkpoint/restart

Gate 3F passed in Unity job `63702483`. Gate 3G verifies that the full live
dynamic-domain calculation can stop at a physical feedback-window boundary,
recover, and continue without duplicating or omitting a coupling step.

## Restart contract

Two independent copies of the verified Gate 3F physical state are used. The
continuous copy advances logical coupling steps 1 through 1000. The split copy
advances 1 through 600, writes both OpenFOAM fields/cloud data and an explicit
Gate 3G coupling checkpoint, then resumes at step 601 and ends at step 1000.

The explicit checkpoint uses the versioned `GATE3G_STATE_V1` format and stores
all 64 dynamic layer requests and all 64 fractional reservoir accumulators.
The restart refuses a missing file, a wrong version, a wrong step, a wrong
entry count, a nonphysical layer request, or a nonfinite accumulator.

OpenFOAM writes the continuum fields and DSMC cloud at the aligned 600-step
boundary. The coupling checkpoint therefore carries only state not owned by
the native OpenFOAM case.

## Statistical equivalence

DSMC is stochastic, so Gate 3G does not claim a byte-identical particle cloud.
It requires exact coupling-step coverage, exact adaptive-layer inventories,
zero inactive parcels, a zero ownership-ledger error, and conservation within
`1e-12` in every segment. Post-restart physical wall-flux checksums and the
final parcel population must agree with the continuous run inside declared
finite-sample tolerances. The summary explicitly records
`restart_matches_continuous_byte_for_byte=false`.

## Parallel audit

The dynamic particle-ownership and checkpoint kernel is executed on one, two,
and four MPI ranks. The rank-independent integer checksum and zero ownership
balance are acceptance criteria. Timing and speedup are reported, but no
efficiency threshold is imposed on this short single-node audit. This is not a
claim of whole-solver domain-decomposition scaling.

## Acceptance

Gate 3G passes only if:

- the continuous, fresh, and restarted live MPMD segments all complete;
- fresh step 600 is followed by restart step 601 and final step 1000;
- the versioned 64-point coupling state is restored;
- every segment retains exact particle ownership and zero inactive inventory;
- the stochastic physical result agrees with the continuous run inside the
  declared sampling tolerance; and
- one-, two-, and four-rank kernel checksums are identical.
