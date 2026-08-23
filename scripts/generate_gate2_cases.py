#!/usr/bin/env python3
"""Generate the immutable Gate 2 continuum and adaptive DSMC cases."""

from __future__ import annotations

import argparse
from pathlib import Path

from generate_gate1c_cases import FULL_HEIGHT, make_continuum, make_kinetic


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"expected exactly one {old!r} in {path}")
    path.write_text(text.replace(old, new), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("run_directory", type=Path)
    args = parser.parse_args()
    root = args.run_directory.resolve()
    if root.exists():
        raise SystemExit(f"refusing to overwrite existing run directory: {root}")
    root.mkdir(parents=True)

    continuum = root / "continuum"
    adaptive = root / "adaptive"
    make_continuum(continuum)
    make_kinetic(adaptive, FULL_HEIGHT, 20, "farfield", False)

    # Retain every physical snapshot used by the forward/reverse hysteresis
    # replay.  The Gate 1C generator keeps only two snapshots by design.
    replace_once(
        continuum / "system/controlDict",
        "purgeWrite          2;",
        "purgeWrite          0;",
    )
    replace_once(
        adaptive / "system/controlDict",
        "application         dsmcFoamGate1C;",
        "application         gate2ParticleManager;",
    )
    (adaptive / "system/gate2Properties").write_text(
        """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    \"system\";
    object      gate2Properties;
}

activationThreshold     0.05;
deactivationThreshold   0.03;
minimumLayers           1;
haloLayers              1;
maximumOverlapZ         1.0;
""",
        encoding="utf-8",
    )
    print(f"GATE2_CASES={root}")


if __name__ == "__main__":
    main()
