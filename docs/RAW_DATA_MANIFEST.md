# Raw DS2V snapshot manifest

The analysis uses Mach-10 nitrogen cylinder records at:

| Kn_D | snapshots available | dt* |
|---:|---:|---:|
| 0.010 | 200 | 0.288 |
| 0.025 | 600 | 0.239695 |
| 0.050 | 419 | 0.430857 |
| 0.075 | 674 | 0.491165 |
| 0.100 | 400 | 0.369 |
| 0.150 | 703 | 0.389148 |
| 0.250 | 462 | 0.443 |
| 0.500 | 350 | 0.508 |
| 1.000 | 283 | 0.789 |

Expected files are Tecplot POINT-format `*_snapshot_*_DS2FF.DAT` outputs plus `MODAL_OUTPUT_LOG.csv`. Raw snapshots are excluded from Git because of storage size and GitHub's per-file limits.
