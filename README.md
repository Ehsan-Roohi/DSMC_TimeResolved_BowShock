# DSMC Time-Resolved Bow-Shock Dynamics

Reproducibility archive for the manuscript:

**A slow collective displacement coordinate in a broadening rarefied hypersonic bow-shock layer**

- **Ahmad Shoja-Sani** (first author)
- **Ehsan Roohi** (corresponding author)

## Scientific scope

The companion mean-flow paper analyzes rarefaction-induced bow-shock inflation and parameter-space similarity:

- E. Roohi and A. Shoja-Sani, *Rarefaction-induced inflation and similarity breakdown of hypersonic bow shocks over a circular cylinder*, arXiv:2605.17099 (2026).

This repository contains the distinct time-resolved analysis: physical-domain support auditing, temporal coarse graining, correlated-noise covariance inference, collective angular displacement, full-field translation-template validation, multi-moment synchronization, sliding-window persistence, and injection-based detection limits.

Manuscript candidates and running DSMC controls are tracked in
[`RESEARCH_STATUS.md`](RESEARCH_STATUS.md).  They remain outside the default
manuscript until their pre-registered gates are complete.

## Main physical result

Between `Kn_D=0.01` and `0.025`, the mean 10-90 density width increases by 82%, while the normalized collective angular mode retains an absolute normalized inner product of 0.972 and an order-one convective memory. Density and pressure remain strongly coupled to the common displacement; Mach number and translational temperature progressively decouple. The coordinate is weak in raw variance and is interpreted as a noise-excited slow response, not a dominant instability.

## Repository layout

- `manuscript/`: JFM LaTeX source, compiled PDF, figures, tables, and processed manuscript data.
- `analysis/unified/`: all-Knudsen QC, registration, POD, temporal coarse-graining, and covariance scripts.
- `analysis/final_statistical_gate/`: sliding-window and injection/exclusion analyses.
- `analysis/displacement_template/`: full-field multi-moment displacement validation.
- `processed_data/`: compact CSV outputs needed to reproduce manuscript figures and tables.
- `docs/`: provenance, raw-data manifest, and interpretation notes.

## Build the paper

```bash
cd manuscript
latexmk -pdf main.tex
```

If the system BibTeX alternative is broken, run:

```bash
pdflatex main.tex
bibtex main
pdflatex main.tex
pdflatex main.tex
```

## Raw data

The raw DS2V snapshots are multi-gigabyte text files and are not stored in GitHub. `docs/RAW_DATA_MANIFEST.md` records the required cases, counts, and expected naming convention. Edit `analysis/config.example.json` to point to the archived snapshots.
