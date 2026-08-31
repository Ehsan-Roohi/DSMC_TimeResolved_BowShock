# Gate 3N: live gradient-length Knudsen interface

Gate 3N replaces the wall-discrepancy selector with a live continuum-breakdown calculation. Every coupling window, `rhoCentralFoam` computes the hard-sphere argon mean free path (`d=4.17e-10 m`) and the cellwise maximum of density, temperature, and velocity gradient-length Knudsen numbers.

Each of 64 angular columns expands its kinetic region at `Kn_GL >= 0.05` and contracts only below `0.03`. One buffer layer and one-layer-per-window motion are enforced. The run restores the exact Gate 3M state at step 10000 and advances both real solvers to step 12000 in the verified `2+2` layout. PASS requires a nontrivial threshold-driven interface response, all solver/distribution gates, a live OpenFOAM `KnGL` field, and the complete 640-row interface history.
