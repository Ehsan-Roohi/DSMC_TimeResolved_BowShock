# Gate 3D: physical feedback replay and scaling

Gate 3C passed before this gate was defined. Gate 3D uses its completed,
physical hybrid-DSMC wall statistics rather than a manufactured flux profile.
It is the bounded bridge between one-way physical validation and a live
concurrent adaptive co-simulation.

## Data and sign contract

The required `gate3c_wall_comparison.csv` contains 64 cylinder faces and the
full-DSMC and hybrid heat-flux and streamwise force-density block means. For
each 200-step physical window, Gate 3D forms an integrated five-component
packet

`(mass, momentum-x, momentum-y, momentum-z, energy)`.

The current monatomic wall packet has zero mass and transverse-momentum
components. Streamwise impulse and energy are the measured hybrid values times
face area and window duration. MUI transports the packet from the DSMC replay
role to the continuum role. The receiver projects only any global
floating-point residual, relaxes the packet, and writes a deterministic
checkpoint.

The OpenFOAM utility then applies the equal-and-opposite reaction to one
continuum cell per angular face. A single global scale limits the maximum local
momentum or internal-energy correction to 1%. Because the same scale multiplies
every face and component, it preserves the integrated reaction exactly while
preventing negative temperature.

## Adaptive transfer surface

Each face receives a physical discrepancy indicator from the Gate 3C
hybrid/reference difference normalized by the full-DSMC 95% interval and a
profile floor. The requested surface spans four to eight radial layers. Each
coupling window may change only one layer, using the already tested Gate 2/3B
hysteresis and transition contract. MUI points and OpenFOAM target cells use
the resulting face-local radius.

## Acceptance

- Gate 3C physical prerequisite passes unchanged;
- all 64 actual physical feedback packets cross MUI;
- projected, relaxed, and OpenFOAM-application conservation errors are at most
  `1e-12`;
- at least one physical interface layer changes;
- OpenFOAM `p`, `U`, and `T` are written and both velocity and temperature
  change without loss of positivity;
- continuous and checkpoint/restart feedback state and CSV are byte-identical;
  and
- one-, two-, and four-rank coupling-kernel checksums agree within `1e-12`.

Timing is reported, not forced to show ideal speedup for this small 64-face
kernel. A Gate 3D PASS sets the two-way application, adaptive replay, and
coupling-kernel scaling flags true. It deliberately leaves
`live_concurrent_openfoam_dsmc_completed` false; that is Gate 3E.

Unity status: passed in job `63673123` with exit code `0:0`. The maximum
relaxed transport conservation error was `6.7763e-21`, OpenFOAM feedback
application error was `8.2718e-25`, and the restarted state was byte-identical.
See [`docs/results/gate3d_unity_63673123.json`](results/gate3d_unity_63673123.json).
