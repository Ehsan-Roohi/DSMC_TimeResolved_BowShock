# Current JFM verdict after full-record transition analysis

## Firm results

1. The old field-POD condensation is not physical. Corrected field POD is
   high-rank for all nine Knudsen numbers.
2. A noise-separated collective displacement mode is robust at Kn=0.01.
3. The full 600-snapshot Kn=0.025 record confirms the same physical mode:
   - Delta AICc = 59.1, bootstrap interval 29.0–64.4;
   - LOOCV error ratio = 0.58;
   - uniform correlation = 0.876, bootstrap lower bound 0.781;
   - far-angle correlation = 0.267, bootstrap lower bound 0.120;
   - PSD correction is negligible;
   - mode correlation with Kn=0.01 is 0.972.
4. Kn=0.05 does not yield a trustworthy physical covariance:
   LOOCV is much worse than noise-only, PSD correction is 54%, and the
   far-angle bootstrap interval includes zero.
5. Kn=0.075 and 0.10 are time-window dependent and cannot presently be called
   a persistent collective regime.
6. Kn=0.15 is unsupported by the two-component model.

## Journal assessment

A publishable physics result exists. It is no longer a single-point finding:
Kn=0.01 and 0.025 show the same collective displacement mode with an
order-one convective memory.

However, the stronger statement that rarefaction causes the mode to disappear
is not yet demonstrated. Non-detection at Kn>=0.05 must be accompanied by
power-based exclusion limits.

Submitting today:
- Physics of Fluids: strong and realistic.
- Journal of Fluid Mechanics: plausible but still vulnerable because the
  transition mechanism is not quantitatively closed.

The final JFM gate is:
- U90 at Kn=0.05 and above must be below the low-Kn mode amplitude, or
- the paper must avoid a disappearance claim and focus on the emergence and
  structure of the low-Kn collective coordinate.

## One additional physical validation recommended

Test whether the resolved density, Mach, temperature and pressure
perturbations satisfy a displacement template:

q'(s,theta,t) approximately equals -a(t) d qbar / ds.

Agreement at Kn=0.01 and 0.025 would prove that the marker mode represents
translation of the whole compression layer rather than a marker-only
statistical feature.

No further POD, DMD or SPOD campaign is needed.
