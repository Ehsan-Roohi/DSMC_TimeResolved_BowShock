#!/usr/bin/env python3
"""Set controlDict startTime without losing the exact OpenFOAM time name."""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path


START_TIME_RE = re.compile(
    r"(?m)^(?P<indent>[ \t]*)startTime(?P<spacing>[ \t]+)[^;\r\n]+;(?P<tail>[ \t]*)$"
)
NUMBER_RE = re.compile(
    r"^[+-]?(?:(?:\d+(?:\.\d*)?)|(?:\.\d+))(?:[eE][+-]?\d+)?$"
)


def set_start_time(control_dict: Path, time_name: str) -> None:
    if not NUMBER_RE.fullmatch(time_name):
        raise ValueError(f"invalid OpenFOAM time name: {time_name!r}")
    value = float(time_name)
    if not math.isfinite(value) or value < 0.0:
        raise ValueError(f"invalid OpenFOAM time value: {time_name!r}")

    text = control_dict.read_text(encoding="utf-8")

    def replacement(match: re.Match[str]) -> str:
        return (
            f"{match.group('indent')}startTime{match.group('spacing')}"
            f"{time_name};{match.group('tail')}"
        )

    updated, count = START_TIME_RE.subn(replacement, text)
    if count != 1:
        raise ValueError(
            f"expected exactly one startTime entry in {control_dict}, found {count}"
        )
    control_dict.write_text(updated, encoding="utf-8")
    print(f"GATE2_START_TIME={time_name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("control_dict", type=Path)
    parser.add_argument("time_name")
    args = parser.parse_args()
    set_start_time(args.control_dict, args.time_name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
