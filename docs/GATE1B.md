# Gate 1B: real OpenFOAM uniform-equilibrium coupling

Gate 1B promotes the Gate 1A API contract to two real OpenFOAM-v2312
executables. `rhoCentralFoamMUI` and `dsmcFoamMUI` run as a two-program MPI
job and exchange volume-averaged density, velocity, temperature and specific
energy through MUI at every physical time step.

The deterministic case is a 1 mm periodic cube containing monatomic argon at
300 K and 100 m/s. The continuum pressure and DSMC number density represent
the same mass density. `dsmcInitialise` creates the restart fields; at the
initial MUI handoff the kinetic solver replaces its stochastic seed with the
six-velocity moment-exact packet from Gate 1A in every one of the 64 cells.
The resulting 384 real DSMC parcels reproduce the continuum mass, momentum and
monatomic translational energy before both solvers advance for ten time steps.

Gate 1B passes only if:

- both real solver executables complete at least five coupled steps;
- each solver conserves mass, momentum and total energy to `1e-10` relative;
- continuum and DSMC macrostates agree to `1e-3` relative at every step;
- both solver-specific PASS markers are present in the common MPMD log.

This is a uniform-equilibrium numerical gate, not a physical shock or flat
plate validation. Gate 1C introduces the first non-uniform validation case.
