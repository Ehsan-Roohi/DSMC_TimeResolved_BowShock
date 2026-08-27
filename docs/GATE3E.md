# Gate 3E: live concurrent rhoCentralFoam/DSMC coupling

Gate 3D passed in Unity job `63673123`. Gate 3E removes its completed-data
replay: a derived OpenFOAM-v2312 `rhoCentralFoam` and a derived real
`dsmcFoam` remain alive together in one MUI MPMD job for 1000 synchronized
relative-time steps of `1e-7 s` and five feedback windows of `2e-5 s`.

## Live exchange

At every synchronized step the continuum solver advances its ordinary
Kurganov finite-volume equations, samples `p/U/T` at 64 angular locations,
and sends number density, velocity, temperature, and the requested radial
layer count. The DSMC solver uses those live states to inject its reservoir
parcels and then calls the ordinary `dsmcCloud::evolve()`.

Every 200 DSMC steps, 40 physical wall samples are averaged. Their integrated
mass, three momentum components, and energy are returned through the same MUI
interface. One global positivity-preserving scale is applied to the equal and
opposite continuum update. The update modifies `rhoU`, `rhoE`, `U`, `e`, `T`,
and `p` consistently before the next continuum step.

## Adaptive scope

The continuum sampling radius moves between four and eight radial layers with
the bounded Gate 2/3D transition rule. The live DSMC solver receives and
audits the same layer inventory. This gate deliberately retains the validated
Gate 3C DSMC annulus; changing the DSMC mesh/particle ownership while both
solvers run is a later dynamic-domain gate. The machine summary therefore
sets `adaptive_sampling_surface_completed=true` and
`adaptive_particle_domain_completed=false`.

## Acceptance

- the immutable Gate 3D PASS artifact is required;
- both real solvers complete exactly 1000 synchronized steps and five windows;
- every DSMC window contains 40 finite physical wall samples;
- both applications observe at least one adaptive layer change;
- feedback changes continuum velocity and temperature without loss of
  positivity;
- applied momentum and energy agree with the globally scaled reaction packet
  within `1e-12`; and
- MUI reports both `mpi://continuum/gate3e` and `mpi://dsmc/gate3e`.

The runner copies the completed Gate 3C continuum and hybrid cases into a new
non-overwriting Gate 3E run directory and resumes their latest physical state.
