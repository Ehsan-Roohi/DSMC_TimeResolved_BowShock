# V3 revision notes

## Changes completed without new DSMC runs

- Expanded the reference list from 22 to 50 items and added DOI metadata.
- Added the Plotkin--Poggie--Touber stochastic shock-motion lineage and the modern JFM/ARFM shock-unsteadiness literature.
- Added DSMC statistical-error, fluctuating-hydrodynamics and molecular-fluctuation references.
- Added the small-sample AIC, moving/stationary bootstrap, nearest-PSD-covariance and Welch spectral references used by the analysis.
- Reframed the autoregressive marker model as a first-order low-pass stochastic response; the text explicitly states that the analogy is structural and does not identify the forcing mechanism.
- Reduced the abstract to 230 words.
- Removed the in-manuscript Statement of significance and supplied an 82-word standalone file for JFM submission.
- Replaced claims of dynamic invariance and progressive decoherence by two-state consistency and selective weakening of synchrony.
- Clarified that the stored fields are non-overlapping short block averages with accumulator reset, while neighbouring outputs remain correlated through continuous particle states.
- Added a quantitative vibrational-nonequilibrium limitation. The estimated post-shock temperature is comparable to the N2 characteristic vibrational temperature, so the present DS2V gas must be described as rotational model nitrogen.
- Added the live GitHub repository URL.
- Fixed the crowded full-field table and suppressed author-template page-limit warnings in the review PDF.

## Remaining decisive computations

1. Independent-seed repeat at KnD=0.01 with unchanged mesh, particle weight, output cadence and sampling window.
2. Controlled simulator-particle-number scaling, preferably 0.5N, N and 2N, to test whether variance scales with sampling level while mode shape and memory remain stable.
3. Noise-memory calibration sensitivity, including a +/-50% perturbation of phi_n and an alternative upstream/far-field noise proxy.
4. Upstream mass-flux/density forcing to marker lagged correlation and cross-spectrum, together with a Lorentzian/first-order transfer-function diagnostic.
5. A full-domain run without the symmetry boundary is needed only if breathing and antisymmetric rocking must be distinguished; the current upper-half configuration excludes rocking by construction.

The first two controls remain the strongest defence against the interpretation that the collective coordinate is a solver/sampling artefact. The literature and framing revisions do not replace them.
