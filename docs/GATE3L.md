# Gate 3L: whole-solver spatial strong scaling

Gate 3L executes the real coupled rhoCentralFoam and dsmcFoam applications for
1000 physical coupling steps at 1+1, 2+2, and 4+4 ranks. The 1+1 case is the
serial-per-application MPMD baseline. The 2+2 and 4+4 cases use complete
OpenFOAM field and cloud decomposition with independent application sub-worlds.

Wall time covers the complete live MPMD solve, not a proxy kernel. The gate
reports speedup and parallel efficiency without imposing an efficiency cutoff
on this small single-node problem. Every rank layout must retain exact
interface ownership, globally reduced DSMC wall flux, zero particle-ledger
error, zero inactive parcels, and feedback conservation below 1e-12.
Stochastic wall-flux and final parcel counts must remain within declared
finite-sampling tolerances relative to 1+1.
