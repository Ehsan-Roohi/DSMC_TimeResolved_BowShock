from __future__ import annotations
import glob,re,json
from pathlib import Path
from typing import Any


def natural_key(path: str):
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", str(path))]


def parse_kn_label(name: str) -> float:
    m=re.fullmatch(r"Kn(\d+)p(\d+)",name)
    if not m:
        return float("nan")
    return float(f"{int(m.group(1))}.{m.group(2)}")


def load_json(path: str|Path) -> dict[str,Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def save_json(obj: Any,path: str|Path):
    p=Path(path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(obj,indent=2),encoding="utf-8")


def snapshot_files(case: dict) -> list[str]:
    files=sorted(glob.glob(case["pattern"],recursive=True),key=natural_key)
    excludes=case.get("exclude_substrings",["POD_mode","DMD_mode","SPOD_mode","shock_window","mean_rms"])
    return [f for f in files if not any(x.lower() in f.lower() for x in excludes)]
