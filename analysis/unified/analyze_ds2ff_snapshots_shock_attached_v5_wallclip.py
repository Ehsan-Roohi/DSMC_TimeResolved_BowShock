#!/usr/bin/env python3
"""
Shock-window / ray-attached modal analysis for DS2V/DS2FF snapshot files.
NaN-safe v2: drops invalid rays and writes Tecplot-ready finite files.

Purpose
-------
Reads time-ordered DS2FF snapshot files, samples the upstream bow-shock layer
on body-normal rays, maps each snapshot to a common density-attached window,
and computes temporal POD, DMD, and optional POD-subspace SPOD.

Recommended first use for the user's N2 M=10 Kn=0.01 snapshots:

python analyze_ds2ff_snapshots_shock_attached.py \
  --pattern "N2_M10_Kn0p01_snapshot_*_DS2FF.DAT" \
  --out N2_M10_Kn0p01_shock_attached_modal \
  --variables D MA TTR TRT P \
  --theta-min 120 --theta-max 180 --ntheta 61 \
  --xi-min -1 --xi-max 4 --nxi 260 \
  --dt-star 1.0 \
  --n-pod-modes 30 --dmd-rank 40 --n-dmd-modes 30 \
  --write-mode-fields 6 --do-spod

Notes
-----
1. Registration is based on the time-mean density field by default. This avoids
   interpreting DSMC sampling noise as snapshot-by-snapshot shock motion.
2. The output Tecplot files are structured ray/xi windows, not the original
   unstructured DS2FF point cloud.
3. For DMD physical frequencies, set --dt-star to Delta t * U_inf / D. If this
   is unknown, use --dt-star 1 and frequencies are in cycles/snapshot.
"""

from __future__ import annotations

import argparse
import csv
import glob
import math
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Sequence

import numpy as np

try:
    from scipy.spatial import Delaunay, cKDTree
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator
    from scipy.ndimage import gaussian_filter1d
except Exception as e:  # pragma: no cover
    raise SystemExit(
        "This script requires scipy. Install with: pip install scipy\n"
        f"Import error was: {e}"
    )


# ----------------------------- Tecplot parser -----------------------------

@dataclass
class Zone:
    header: str
    npoints: int
    data: np.ndarray


def natural_key(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def parse_variables(lines: List[str]) -> Tuple[List[str], int]:
    """Return variable names and index of first zone line."""
    start = None
    for i, line in enumerate(lines):
        if line.strip().upper().startswith("VARIABLES"):
            start = i
            break
    if start is None:
        raise ValueError("No VARIABLES line found")

    buf = []
    first_zone = None
    for j in range(start, len(lines)):
        if lines[j].strip().upper().startswith("ZONE"):
            first_zone = j
            break
        buf.append(lines[j])
    if first_zone is None:
        raise ValueError("No ZONE line found")

    text = " ".join(buf)
    vars_ = re.findall(r'"([^"]+)"', text)
    if not vars_:
        # Fallback for unquoted variables
        text2 = text.split("=", 1)[-1]
        vars_ = [v.strip().strip(',') for v in text2.split() if v.strip().strip(',')]
    return vars_, first_zone


def parse_zone_npoints(header: str) -> int:
    m = re.search(r"\bI\s*=\s*(\d+)", header, flags=re.IGNORECASE)
    if not m:
        raise ValueError(f"Could not parse I=... from zone header: {header.strip()}")
    return int(m.group(1))


def read_tecplot_point_file(path: str) -> Tuple[List[str], List[Zone]]:
    with open(path, "r", errors="replace") as f:
        lines = f.readlines()

    vars_, idx = parse_variables(lines)
    zones: List[Zone] = []
    nvar = len(vars_)
    i = idx
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if not line.upper().startswith("ZONE"):
            i += 1
            continue
        header = lines[i].rstrip("\n")
        npoints = parse_zone_npoints(header)
        i += 1
        rows = []
        while i < len(lines) and len(rows) < npoints:
            s = lines[i].strip()
            if not s:
                i += 1
                continue
            if s.upper().startswith("ZONE"):
                raise ValueError(
                    f"Zone ended early in {path}: expected {npoints} rows, got {len(rows)}"
                )
            parts = s.replace(",", " ").split()
            if len(parts) < nvar:
                raise ValueError(
                    f"Bad numeric row in {path}, zone {len(zones)+1}: expected {nvar} cols, got {len(parts)}; line={s[:120]}"
                )
            rows.append([float(x) for x in parts[:nvar]])
            i += 1
        if len(rows) != npoints:
            raise ValueError(f"Zone ended early in {path}: expected {npoints}, got {len(rows)}")
        zones.append(Zone(header=header, npoints=npoints, data=np.asarray(rows, dtype=float)))
    if not zones:
        raise ValueError(f"No zones read from {path}")
    return vars_, zones


def write_structured_tecplot(path: str, variables: List[str], data: np.ndarray,
                             nxi: int, ntheta: int, title: str):
    """Write data shape (ntheta,nxi,nvar) as Tecplot POINT zone with I=nxi,J=ntheta."""
    with open(path, "w") as f:
        f.write(f'TITLE = "{title}"\n')
        f.write("VARIABLES = " + " ".join(f'\"{v}\"' for v in variables) + "\n")
        f.write(f'ZONE T="{title}", I={nxi}, J={ntheta}, F=POINT\n')
        for j in range(ntheta):
            for i in range(nxi):
                row = data[j, i, :]
                f.write(" ".join(format_float(x) for x in row) + "\n")


def format_float(x: float) -> str:
    # Tecplot can fail to triangulate/contour when NaN tokens are present in
    # structured point files.  Invalid cells are therefore written as zero in
    # Tecplot outputs; the corresponding valid masks/QC files identify which
    # locations were truly supported by the interpolation.
    if not np.isfinite(x):
        return "0.0000000000e+00"
    return f"{x:.10e}"


# ----------------------------- Input alignment -----------------------------

def validate_or_remap_to_reference(
    file: str,
    zones: List[Zone],
    ref_zones: List[Zone],
    zone_index: int,
    vars_idx: List[int],
    xy_idx: Tuple[int, int],
    grid_tol: float,
    coord_match_tol: float,
    input_remap: str,
) -> Tuple[np.ndarray, Dict[str, float | str]]:
    """Return requested variable data on reference zone grid: shape (npoints,nvars)."""
    z = zones[zone_index]
    zr = ref_zones[zone_index]
    xcol, ycol = xy_idx
    xy = z.data[:, [xcol, ycol]]
    ref_xy = zr.data[:, [xcol, ycol]]
    info: Dict[str, float | str] = {
        "file": os.path.basename(file),
        "npoints": int(z.data.shape[0]),
        "ref_npoints": int(zr.data.shape[0]),
        "alignment": "unknown",
        "ordered_max_abs_dxy": np.nan,
        "nearest_max_dist": np.nan,
        "nearest_p95_dist": np.nan,
        "nearest_median_dist": np.nan,
        "unique_source_fraction": np.nan,
    }

    if xy.shape[0] == ref_xy.shape[0]:
        ordered_max = float(np.nanmax(np.abs(xy - ref_xy)))
        info["ordered_max_abs_dxy"] = ordered_max
        if ordered_max <= grid_tol:
            info["alignment"] = "ordered"
            return z.data[:, vars_idx], info

        # Try exact coordinate-set alignment through lexicographic sort.
        order = np.lexsort((xy[:, 1], xy[:, 0]))
        ref_order = np.lexsort((ref_xy[:, 1], ref_xy[:, 0]))
        sorted_max = float(np.nanmax(np.abs(xy[order] - ref_xy[ref_order])))
        if sorted_max <= coord_match_tol:
            aligned = np.empty_like(z.data[:, vars_idx])
            # source sorted order corresponds to reference sorted order
            aligned[ref_order, :] = z.data[order][:, vars_idx]
            info["alignment"] = "sortxy_reordered"
            info["nearest_max_dist"] = sorted_max
            return aligned, info

    if input_remap == "none":
        raise ValueError(
            f"{file}: zone {zone_index+1} is not compatible with reference. "
            "Use --input-remap nearest to remap snapshots to the reference grid."
        )

    # Nearest remap to reference point cloud.
    tree = cKDTree(xy)
    dist, ind = tree.query(ref_xy, k=1)
    if not np.all(np.isfinite(dist)):
        raise ValueError(f"{file}: nearest remap failed with non-finite distances")
    aligned = z.data[ind][:, vars_idx]
    info["alignment"] = "nearest_remap_to_reference"
    info["nearest_max_dist"] = float(np.max(dist))
    info["nearest_p95_dist"] = float(np.percentile(dist, 95))
    info["nearest_median_dist"] = float(np.median(dist))
    info["unique_source_fraction"] = float(len(np.unique(ind)) / max(1, len(ind)))
    return aligned, info


# ----------------------------- Ray extraction -----------------------------

def build_interpolators(xy: np.ndarray, values: np.ndarray, tri: Delaunay, method: str = "linear"):
    if method == "nearest":
        return NearestNDInterpolator(xy, values)
    return LinearNDInterpolator(tri, values, fill_value=np.nan)


def ray_points(xc: float, yc: float, R: float, theta_deg: float, s: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    th = np.deg2rad(theta_deg)
    r = R + s
    x = xc + r * np.cos(th)
    y = yc + r * np.sin(th)
    return x, y


def moving_valid_median(a: np.ndarray) -> float:
    a = np.asarray(a)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return np.nan
    return float(np.median(a))


def _interp_crossing(ss: np.ndarray, qstar: np.ndarray, target: float, search: np.ndarray) -> float:
    """Return s where qstar crosses target inside search; robust to increasing/decreasing profiles."""
    idx = np.where(search & np.isfinite(qstar))[0]
    if idx.size < 2:
        return np.nan
    z = qstar - target
    candidates = []
    for a, b in zip(idx[:-1], idx[1:]):
        if b != a + 1:
            continue
        za, zb = z[a], z[b]
        if not (np.isfinite(za) and np.isfinite(zb)):
            continue
        if za == 0:
            candidates.append(float(ss[a])); continue
        if zb == 0:
            candidates.append(float(ss[b])); continue
        if za * zb < 0:
            t = abs(za) / (abs(za) + abs(zb))
            candidates.append(float(ss[a] + t * (ss[b] - ss[a])))
    if candidates:
        return float(np.median(candidates))
    k = idx[np.nanargmin(np.abs(z[idx]))]
    return float(ss[k])


def _crossing_width(ss: np.ndarray, qstar: np.ndarray, search: np.ndarray,
                    low: float, high: float) -> float:
    s_low = _interp_crossing(ss, qstar, low, search)
    s_high = _interp_crossing(ss, qstar, high, search)
    if np.isfinite(s_low) and np.isfinite(s_high) and abs(s_low - s_high) > 0:
        return float(abs(s_low - s_high))
    return np.nan


def compute_mean_density_metrics(
    xy: np.ndarray,
    rho_mean: np.ndarray,
    xc: float,
    yc: float,
    R: float,
    theta_vals: np.ndarray,
    nr_raw: int,
    smax_R: float,
    wall_exclude_R: float,
    smooth_sigma: float,
    search_far_fraction: float,
    marker: str = "hybrid",
    width_mode: str = "hybrid",
    half_level: float = 0.5,
    transition_low: float = 0.1,
    transition_high: float = 0.9,
    edge_guard_R: float = 0.03,
    centroid_grad_frac: float = 0.25,
) -> Tuple[np.ndarray, Dict[str, np.ndarray]]:
    """Locate a density-based compression-layer marker on the time-mean field."""
    tri = Delaunay(xy)
    interp = build_interpolators(xy, rho_mean, tri, method="linear")
    s_raw = np.linspace(0.0, smax_R * R, nr_raw)

    ntheta = len(theta_vals)
    s_peak = np.full(ntheta, np.nan)
    delta = np.full(ntheta, np.nan)
    rho_up = np.full(ntheta, np.nan)
    rho_down = np.full(ntheta, np.nan)
    maxgrad = np.full(ntheta, np.nan)
    valid_fraction = np.full(ntheta, np.nan)
    marker_used = np.full(ntheta, "invalid", dtype=object)
    boundary_hit = np.full(ntheta, np.nan)
    s_half = np.full(ntheta, np.nan)
    s_centroid = np.full(ntheta, np.nan)
    delta_grad = np.full(ntheta, np.nan)
    delta_transition = np.full(ntheta, np.nan)
    qstar_at_marker = np.full(ntheta, np.nan)
    search_s_min = np.full(ntheta, np.nan)
    search_s_max = np.full(ntheta, np.nan)

    for j, th in enumerate(theta_vals):
        x, y = ray_points(xc, yc, R, th, s_raw)
        prof = interp(x, y)
        valid = np.isfinite(prof)
        valid_fraction[j] = float(np.mean(valid))
        if np.count_nonzero(valid) < max(30, nr_raw // 20):
            continue

        idx = np.where(valid)[0]
        breaks = np.where(np.diff(idx) > 1)[0]
        starts = np.r_[0, breaks + 1]
        ends = np.r_[breaks, len(idx) - 1]
        lengths = ends - starts + 1
        k = int(np.argmax(lengths))
        run_idx = idx[starts[k]: ends[k] + 1]
        if run_idx.size < max(30, nr_raw // 20):
            continue
        ss = s_raw[run_idx]
        pp = prof[run_idx]

        pp_s = gaussian_filter1d(pp, sigma=smooth_sigma, mode="nearest") if smooth_sigma > 0 else pp.copy()
        grad = np.gradient(pp_s, ss)
        s_len = ss[-1] - ss[0]
        search = (ss >= wall_exclude_R * R) & (ss <= ss[0] + search_far_fraction * s_len)
        if np.count_nonzero(search) < 5:
            continue
        smin = float(np.nanmin(ss[search])); smax = float(np.nanmax(ss[search]))
        search_s_min[j] = smin; search_s_max[j] = smax

        gabs = np.abs(grad)
        loc_candidates = np.where(search & np.isfinite(gabs))[0]
        if loc_candidates.size == 0:
            continue
        imax = loc_candidates[np.argmax(gabs[loc_candidates])]
        gmax = float(gabs[imax])
        if not np.isfinite(gmax) or gmax <= 0:
            continue
        maxgrad[j] = gmax

        # Downstream/post-shock state: just outside the wall-exclusion interval.
        # Upstream state: far-field tail.  This avoids using the wall jump itself.
        down_mask = (ss >= smin) & (ss <= min(smax, smin + 0.20 * R))
        if np.count_nonzero(down_mask) < 5:
            down_mask = (ss >= ss[0] + 0.03 * s_len) & (ss <= ss[0] + 0.23 * s_len)
        up_mask = ss >= ss[0] + 0.85 * s_len
        rd = moving_valid_median(pp_s[down_mask])
        ru = moving_valid_median(pp_s[up_mask])
        rho_down[j] = rd; rho_up[j] = ru
        jump = rd - ru if (np.isfinite(rd) and np.isfinite(ru)) else np.nan
        if not (np.isfinite(jump) and abs(jump) > 1e-300):
            continue

        qstar = (pp_s - ru) / jump
        s_half_j = _interp_crossing(ss, qstar, half_level, search)
        s_half[j] = s_half_j
        width_j = _crossing_width(ss, qstar, search, transition_low, transition_high)
        delta_transition[j] = width_j
        delta_grad[j] = abs(jump) / gmax

        # Gradient centroid, using only the main gradient support.
        thr = centroid_grad_frac * gmax
        cmask = search & np.isfinite(gabs) & (gabs >= thr)
        if np.count_nonzero(cmask) >= 3 and np.nansum(gabs[cmask]) > 0:
            s_centroid[j] = float(np.nansum(ss[cmask] * gabs[cmask]) / np.nansum(gabs[cmask]))

        edge_guard = edge_guard_R * R
        hit = (abs(ss[imax] - smin) <= edge_guard) or (abs(ss[imax] - smax) <= edge_guard)
        boundary_hit[j] = 1.0 if hit else 0.0

        chosen = np.nan; used = "invalid"
        if marker == "maxgrad":
            chosen = float(ss[imax]); used = "maxgrad"
        elif marker == "halfjump":
            chosen = s_half_j; used = "halfjump"
        elif marker == "gradcentroid":
            chosen = s_centroid[j]; used = "gradcentroid"
        elif marker == "hybrid":
            if hit and np.isfinite(s_half_j):
                chosen = s_half_j; used = "hybrid_halfjump_edgehit"
            else:
                chosen = float(ss[imax]); used = "hybrid_maxgrad"
        else:
            raise ValueError(f"Unknown marker mode {marker!r}")

        if not np.isfinite(chosen):
            if np.isfinite(s_centroid[j]):
                chosen = s_centroid[j]; used = used + "_fallback_centroid"
            else:
                chosen = float(ss[imax]); used = used + "_fallback_maxgrad"

        s_peak[j] = chosen
        marker_used[j] = used
        if np.isfinite(chosen):
            qstar_at_marker[j] = float(np.interp(chosen, ss, qstar))

        if width_mode == "gradient":
            delta[j] = delta_grad[j]
        elif width_mode == "transition":
            delta[j] = delta_transition[j]
        elif width_mode == "hybrid":
            if ("halfjump" in used) and np.isfinite(delta_transition[j]) and delta_transition[j] > 0:
                delta[j] = delta_transition[j]
            elif np.isfinite(delta_grad[j]) and delta_grad[j] > 0:
                delta[j] = delta_grad[j]
            else:
                delta[j] = delta_transition[j]
        else:
            raise ValueError(f"Unknown width mode {width_mode!r}")

        if not (np.isfinite(delta[j]) and delta[j] > 0):
            if np.isfinite(delta_transition[j]) and delta_transition[j] > 0:
                delta[j] = delta_transition[j]
            elif np.isfinite(delta_grad[j]) and delta_grad[j] > 0:
                delta[j] = delta_grad[j]

    metrics = {
        "theta_deg": theta_vals,
        "s_peak": s_peak,
        "delta_rho": delta,
        "rho_up": rho_up,
        "rho_down": rho_down,
        "max_abs_drho_ds": maxgrad,
        "valid_fraction": valid_fraction,
        "marker_used": marker_used,
        "boundary_hit": boundary_hit,
        "s_half": s_half,
        "s_centroid": s_centroid,
        "delta_grad": delta_grad,
        "delta_transition": delta_transition,
        "qstar_at_marker": qstar_at_marker,
        "search_s_min": search_s_min,
        "search_s_max": search_s_max,
    }
    return s_raw, metrics


def sample_attached_snapshots(
    xy: np.ndarray,
    snapshots_refgrid: np.ndarray,  # (nsnap,npoint,nvar)
    var_names: List[str],
    xc: float,
    yc: float,
    R: float,
    theta_vals: np.ndarray,
    xi_vals: np.ndarray,
    s_peak: np.ndarray,
    delta: np.ndarray,
    interp_method: str,
    physical_wall_buffer_R: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return cube shape (nsnap,nvar,ntheta,nxi), xwin/ywin/swin shape (ntheta,nxi)."""
    nsnap, npoint, nvar = snapshots_refgrid.shape
    ntheta, nxi = len(theta_vals), len(xi_vals)
    cube = np.full((nsnap, nvar, ntheta, nxi), np.nan, dtype=float)
    xwin = np.full((ntheta, nxi), np.nan)
    ywin = np.full((ntheta, nxi), np.nan)
    swin = np.full((ntheta, nxi), np.nan)

    for j, th in enumerate(theta_vals):
        if not (np.isfinite(s_peak[j]) and np.isfinite(delta[j]) and delta[j] > 0):
            continue
        s_att = s_peak[j] + xi_vals * delta[j]
        # Clip the attached window to the physical gas domain.
        # s is the outward normal distance measured from the cylinder wall.
        gas_mask = np.isfinite(s_att) & (s_att >= physical_wall_buffer_R * R)
        x_att = np.full_like(s_att, np.nan, dtype=float)
        y_att = np.full_like(s_att, np.nan, dtype=float)
        if np.any(gas_mask):
            xg, yg = ray_points(xc, yc, R, th, s_att[gas_mask])
            x_att[gas_mask] = xg
            y_att[gas_mask] = yg
        xwin[j, :] = x_att
        ywin[j, :] = y_att
        swin[j, gas_mask] = s_att[gas_mask]

    tri = Delaunay(xy)
    points_eval = np.column_stack([xwin.ravel(), ywin.ravel()])
    eval_finite = np.all(np.isfinite(points_eval), axis=1)

    for k in range(nsnap):
        for vi in range(nvar):
            vals = snapshots_refgrid[k, :, vi]
            interp = build_interpolators(xy, vals, tri, method=interp_method)
            out = np.full(points_eval.shape[0], np.nan)
            if np.any(eval_finite):
                out[eval_finite] = interp(points_eval[eval_finite, 0], points_eval[eval_finite, 1])
            cube[k, vi, :, :] = out.reshape(ntheta, nxi)
    return cube, xwin, ywin, swin


# ----------------------------- Modal analysis -----------------------------

def build_feature_matrix(cube: np.ndarray, var_names: List[str], scale_mode: str):
    """Return X features x snapshots, mean/rms cubes, and reconstruction metadata."""
    nsnap, nvar, ntheta, nxi = cube.shape
    mean_cube = np.nanmean(cube, axis=0)
    fluct = cube - mean_cube[None, :, :, :]
    rms_cube = np.sqrt(np.nanmean(fluct ** 2, axis=0))

    valid_cube = np.all(np.isfinite(cube), axis=0)  # nvar,ntheta,nxi
    feature_blocks = []
    meta = []
    scales = []
    for vi, vn in enumerate(var_names):
        valid_flat = valid_cube[vi].ravel()
        idx = np.where(valid_flat)[0]
        if idx.size == 0:
            continue
        arr = fluct[:, vi, :, :].reshape(nsnap, -1)[:, idx]  # nsnap x nfeat_var
        if scale_mode == "variable_rms":
            sc = float(np.sqrt(np.nanmean(arr ** 2)))
            if not np.isfinite(sc) or sc <= 0:
                sc = 1.0
        elif scale_mode == "none":
            sc = 1.0
        else:
            raise ValueError(f"Unknown scale mode: {scale_mode}")
        feature_blocks.append((arr / sc).T)
        meta.append({"var_index": vi, "var_name": vn, "flat_indices": idx, "scale": sc})
        scales.append(sc)

    if not feature_blocks:
        raise ValueError("No common valid shock-window features were found. Try a smaller xi window or wider ray sector.")
    X = np.vstack(feature_blocks)  # features x snapshots
    return X, mean_cube, rms_cube, valid_cube, meta


def vector_to_cube(vec: np.ndarray, meta: List[dict], nvar: int, ntheta: int, nxi: int, unscale: bool = True) -> np.ndarray:
    out = np.full((nvar, ntheta, nxi), np.nan, dtype=complex if np.iscomplexobj(vec) else float)
    pos = 0
    for m in meta:
        idx = m["flat_indices"]
        n = len(idx)
        vals = vec[pos:pos+n]
        if unscale:
            vals = vals * m["scale"]
        flat = out[m["var_index"]].reshape(-1)
        flat[idx] = vals
        out[m["var_index"]] = flat.reshape(ntheta, nxi)
        pos += n
    return out


def write_window_field(path: str, theta_vals: np.ndarray, xi_vals: np.ndarray,
                       xwin: np.ndarray, ywin: np.ndarray, swin: np.ndarray,
                       var_data: Dict[str, np.ndarray], title: str):
    """var_data values shape (ntheta,nxi)."""
    ntheta, nxi = len(theta_vals), len(xi_vals)
    base_vars = ["theta_deg", "xi", "X", "Y", "s"]
    variables = base_vars + list(var_data.keys())
    data = np.full((ntheta, nxi, len(variables)), np.nan)
    for j, th in enumerate(theta_vals):
        data[j, :, 0] = th
        data[j, :, 1] = xi_vals
        data[j, :, 2] = xwin[j, :]
        data[j, :, 3] = ywin[j, :]
        data[j, :, 4] = swin[j, :]
    for k, name in enumerate(var_data.keys(), start=5):
        data[:, :, k] = var_data[name]
    write_structured_tecplot(path, variables, data, nxi=nxi, ntheta=ntheta, title=title)


def run_pod(X: np.ndarray):
    U, S, Vh = np.linalg.svd(X, full_matrices=False)
    eig = S ** 2
    energy = eig / np.sum(eig) if np.sum(eig) > 0 else eig
    coeff = (S[:, None] * Vh)
    return U, S, Vh, energy, coeff


def run_dmd(X: np.ndarray, dt: float, rank: int):
    X1 = X[:, :-1]
    X2 = X[:, 1:]
    U, S, Vh = np.linalg.svd(X1, full_matrices=False)
    r = min(rank, np.sum(S > (np.max(S) * 1e-12)), len(S))
    if r < 1:
        raise ValueError("DMD rank became zero")
    Ur = U[:, :r]
    Sr = S[:r]
    Vr = Vh.conj().T[:, :r]
    Atilde = Ur.conj().T @ X2 @ Vr @ np.diag(1.0 / Sr)
    eigvals, W = np.linalg.eig(Atilde)
    Phi = X2 @ Vr @ np.diag(1.0 / Sr) @ W
    # initial amplitudes
    try:
        b = np.linalg.lstsq(Phi, X[:, 0], rcond=None)[0]
    except Exception:
        b = np.full(eigvals.shape, np.nan + 1j*np.nan)
    omega = np.log(eigvals) / dt
    freq = np.imag(omega) / (2 * np.pi)
    growth = np.real(omega)
    return eigvals, omega, freq, growth, Phi, b, S


def run_spod_in_pod_subspace(coeff: np.ndarray, pod_modes: np.ndarray, pod_energy: np.ndarray,
                             nfft: int, overlap: float, dt: float, pod_rank: int):
    """SPOD using POD temporal coefficients. coeff shape modes x snapshots."""
    r = min(pod_rank, coeff.shape[0])
    A = coeff[:r, :]
    n = A.shape[1]
    nfft = min(nfft, n)
    step = max(1, int(nfft * (1 - overlap)))
    starts = list(range(0, n - nfft + 1, step))
    if len(starts) < 2:
        starts = [0]
    window = np.hanning(nfft)
    win_norm = np.sqrt(np.mean(window ** 2)) if np.mean(window ** 2) > 0 else 1.0
    freqs = np.fft.rfftfreq(nfft, d=dt)
    nfreq = len(freqs)
    lead_eval = np.zeros(nfreq)
    total_power = np.zeros(nfreq)
    lead_vecs = np.zeros((nfreq, r), dtype=complex)

    # Transform each segment in low-rank coefficient space.
    seg_fft = []
    for st in starts:
        seg = A[:, st:st+nfft] * window[None, :] / win_norm
        F = np.fft.rfft(seg, axis=1) / np.sqrt(nfft)
        seg_fft.append(F)  # r x nfreq

    for fi in range(nfreq):
        Q = np.column_stack([F[:, fi] for F in seg_fft])  # r x nseg
        C = (Q @ Q.conj().T) / max(1, Q.shape[1])
        vals, vecs = np.linalg.eigh(C)
        order = np.argsort(vals)[::-1]
        vals = vals[order]
        vecs = vecs[:, order]
        lead_eval[fi] = float(np.real(vals[0])) if vals.size else 0.0
        total_power[fi] = float(np.real(np.sum(vals))) if vals.size else 0.0
        if vals.size:
            lead_vecs[fi, :] = vecs[:, 0]
    return freqs, lead_eval, total_power, lead_vecs, starts, nfft


# ----------------------------- Main -----------------------------

def main():
    ap = argparse.ArgumentParser(description="Shock-attached modal analysis of DS2FF snapshot files")
    ap.add_argument("--pattern", required=True, help="Glob pattern for DS2FF snapshot files")
    ap.add_argument("--start-index", type=int, default=0, help="0-based first snapshot after natural sorting")
    ap.add_argument("--count", type=int, default=0, help="Number of consecutive snapshots to use; 0 means all remaining")
    ap.add_argument("--out", required=True, help="Output directory")
    ap.add_argument("--variables", nargs="+", default=["D", "MA", "TTR", "TRT", "P"],
                    help="DS2FF variable names to include in modal analysis")
    ap.add_argument("--zone", type=int, default=1, help="Tecplot zone number for main field, 1-based")
    ap.add_argument("--xc", type=float, default=0.1524, help="Cylinder center x [m]")
    ap.add_argument("--yc", type=float, default=0.0, help="Cylinder center y [m]")
    ap.add_argument("--R", type=float, default=0.1524, help="Cylinder radius [m]")
    ap.add_argument("--theta-min", type=float, default=120.0)
    ap.add_argument("--theta-max", type=float, default=180.0)
    ap.add_argument("--ntheta", type=int, default=61)
    ap.add_argument("--xi-min", type=float, default=-1.0)
    ap.add_argument("--xi-max", type=float, default=4.0)
    ap.add_argument("--nxi", type=int, default=260)
    ap.add_argument("--physical-wall-buffer-R", type=float, default=0.02,
                    help="Retain only attached-window locations with physical wall-normal distance "
                         "s/R greater than or equal to this value. Recommended primary value: 0.02.")
    ap.add_argument("--nr-raw", type=int, default=900, help="Raw ray samples for locating density-gradient marker")
    ap.add_argument("--smax-R", type=float, default=8.0, help="Maximum ray distance from wall in units of R")
    ap.add_argument("--wall-exclude-R", type=float, default=0.15,
                    help="Near-wall exclusion in units of R for locating the density-gradient shock marker. Default 0.15 avoids selecting the wall/boundary-layer gradient.")
    ap.add_argument("--marker", choices=["maxgrad", "halfjump", "gradcentroid", "hybrid"], default="hybrid",
                    help="Density-layer registration marker. For Kn>=0.1 use halfjump or hybrid; maxgrad is the old low-Kn ridge marker.")
    ap.add_argument("--width-mode", choices=["gradient", "transition", "hybrid"], default="hybrid",
                    help="Scale delta_rho used for xi. transition uses robust 10-90 density transition width.")
    ap.add_argument("--half-level", type=float, default=0.5)
    ap.add_argument("--transition-low", type=float, default=0.1)
    ap.add_argument("--transition-high", type=float, default=0.9)
    ap.add_argument("--edge-guard-R", type=float, default=0.03,
                    help="Hybrid switches away from maxgrad if the maximum lies this close to a search edge, in units of R.")
    ap.add_argument("--centroid-grad-frac", type=float, default=0.25)
    ap.add_argument("--smooth-sigma", type=float, default=4.0, help="Gaussian smoothing sigma in raw ray-index units")
    ap.add_argument("--search-far-fraction", type=float, default=0.94)
    ap.add_argument("--drop-invalid-rays", dest="drop_invalid_rays", action="store_true", default=True,
                    help="Drop rays whose registration marker is invalid before modal analysis. Default: on.")
    ap.add_argument("--keep-invalid-rays", dest="drop_invalid_rays", action="store_false",
                    help="Keep invalid rays in output window. Not recommended for Tecplot.")
    ap.add_argument("--min-ray-valid-fraction", type=float, default=0.05,
                    help="Minimum raw-ray valid fraction required to keep a theta ray.")
    ap.add_argument("--warn-speak-R", type=float, default=0.05,
                    help="Warn if median s_peak/R is smaller than this; usually indicates wall-gradient registration.")
    ap.add_argument("--interp", choices=["linear", "nearest"], default="linear", help="Interpolation from DS2FF points to rays")
    ap.add_argument("--input-remap", choices=["none", "nearest"], default="nearest",
                    help="How to handle input snapshots not on identical ordered XY grid")
    ap.add_argument("--grid-tol", type=float, default=1e-10)
    ap.add_argument("--coord-match-tol", type=float, default=1e-8)
    ap.add_argument("--scale", choices=["variable_rms", "none"], default="variable_rms")
    ap.add_argument("--dt-star", type=float, default=1.0, help="Snapshot spacing in nondimensional time, or 1 for cycles/snapshot")
    ap.add_argument("--n-pod-modes", type=int, default=30)
    ap.add_argument("--dmd-rank", type=int, default=40)
    ap.add_argument("--n-dmd-modes", type=int, default=30)
    ap.add_argument("--write-mode-fields", type=int, default=6)
    ap.add_argument("--do-spod", action="store_true")
    ap.add_argument("--spod-nfft", type=int, default=64)
    ap.add_argument("--spod-overlap", type=float, default=0.5)
    ap.add_argument("--spod-pod-rank", type=int, default=50)
    args = ap.parse_args()

    files = sorted(glob.glob(args.pattern), key=natural_key)
    if args.start_index < 0:
        raise SystemExit("--start-index must be >= 0")
    files = files[args.start_index:]
    if args.count > 0:
        files = files[:args.count]
    if len(files) < 3:
        raise SystemExit(f"Need at least 3 snapshot files, found {len(files)} for pattern {args.pattern}")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # Read all files and selected zone.
    all_vars = None
    all_zones: List[List[Zone]] = []
    for f in files:
        vars_, zones = read_tecplot_point_file(f)
        if all_vars is None:
            all_vars = vars_
        elif vars_ != all_vars:
            raise ValueError(f"Variable list mismatch in {f}")
        all_zones.append(zones)

    assert all_vars is not None
    zone_index = args.zone - 1
    if zone_index < 0 or zone_index >= len(all_zones[0]):
        raise ValueError(f"Requested zone {args.zone}, but first file has {len(all_zones[0])} zones")

    requested_variables = list(args.variables)
    nvar = len(requested_variables)
    load_variables = requested_variables if "D" in requested_variables else ["D"] + requested_variables
    for v in ["X", "Y"] + load_variables:
        if v not in all_vars:
            raise ValueError(f"Variable {v!r} not found. Available variables: {all_vars}")
    xidx = all_vars.index("X")
    yidx = all_vars.index("Y")
    vidx = [all_vars.index(v) for v in load_variables]

    ref_zones = all_zones[0]
    ref_xy = ref_zones[zone_index].data[:, [xidx, yidx]]
    nsnap = len(files)
    npoint = ref_xy.shape[0]
    nload = len(load_variables)
    snapshots = np.full((nsnap, npoint, nload), np.nan)
    qc_rows = []
    for k, (f, zones) in enumerate(zip(files, all_zones)):
        data_aligned, info = validate_or_remap_to_reference(
            f, zones, ref_zones, zone_index, vidx, (xidx, yidx),
            args.grid_tol, args.coord_match_tol, args.input_remap
        )
        snapshots[k, :, :] = data_aligned
        info["snapshot_index"] = k + 1
        qc_rows.append(info)

    with open(out / "snapshot_input_grid_qc.csv", "w", newline="") as fp:
        fieldnames = ["snapshot_index", "file", "npoints", "ref_npoints", "alignment",
                      "ordered_max_abs_dxy", "nearest_max_dist", "nearest_p95_dist",
                      "nearest_median_dist", "unique_source_fraction"]
        wr = csv.DictWriter(fp, fieldnames=fieldnames)
        wr.writeheader()
        for r in qc_rows:
            wr.writerow({k: r.get(k, "") for k in fieldnames})

    # Time-mean density is always loaded as an auxiliary registration field.
    mean_ref = np.nanmean(snapshots, axis=0)  # npoint,nload
    rho_mean = mean_ref[:, load_variables.index("D")]

    theta_vals = np.linspace(args.theta_min, args.theta_max, args.ntheta)
    xi_vals = np.linspace(args.xi_min, args.xi_max, args.nxi)

    _, metrics = compute_mean_density_metrics(
        ref_xy, rho_mean, args.xc, args.yc, args.R, theta_vals,
        args.nr_raw, args.smax_R, args.wall_exclude_R, args.smooth_sigma,
        args.search_far_fraction, args.marker, args.width_mode,
        args.half_level, args.transition_low, args.transition_high,
        args.edge_guard_R, args.centroid_grad_frac,
    )
    # Save all attempted registration rays first.  Some rays (often exactly
    # theta=180 on a half-domain symmetry line) may be unsupported by the
    # unstructured DS2FF point cloud and must be dropped for a NaN-free window.
    keys = ["theta_deg", "s_peak", "delta_rho", "rho_up", "rho_down", "max_abs_drho_ds", "valid_fraction",
            "marker_used", "boundary_hit", "s_half", "s_centroid", "delta_grad", "delta_transition",
            "qstar_at_marker", "search_s_min", "search_s_max"]
    with open(out / "ray_density_registration_metrics_all.csv", "w", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=keys)
        wr.writeheader()
        for j in range(len(theta_vals)):
            wr.writerow({k: metrics[k][j] for k in keys})

    ray_ok = (np.isfinite(metrics["s_peak"]) & np.isfinite(metrics["delta_rho"]) &
              (metrics["delta_rho"] > 0.0) &
              (np.asarray(metrics["valid_fraction"]) >= args.min_ray_valid_fraction))
    n_rays_before = len(theta_vals)
    if args.drop_invalid_rays:
        if np.count_nonzero(ray_ok) < 3:
            raise ValueError("Fewer than three valid shock-attached rays remain. Try theta range away from the symmetry line, --interp nearest, or a smaller wall exclusion.")
        theta_vals = theta_vals[ray_ok]
        for kk in list(metrics.keys()):
            metrics[kk] = np.asarray(metrics[kk])[ray_ok]

    with open(out / "ray_density_registration_metrics.csv", "w", newline="") as fp:
        wr = csv.DictWriter(fp, fieldnames=keys)
        wr.writeheader()
        for j in range(len(theta_vals)):
            wr.writerow({k: metrics[k][j] for k in keys})

    # Registration QC.
    med_speak_R = float(np.nanmedian(metrics["s_peak"] / args.R)) if len(theta_vals) else np.nan
    med_delta_R = float(np.nanmedian(metrics["delta_rho"] / args.R)) if len(theta_vals) else np.nan
    boundary_frac = float(np.nanmean(metrics.get("boundary_hit", np.array([np.nan])))) if len(theta_vals) else np.nan
    with open(out / "registration_qc.txt", "w") as fp:
        fp.write(f"rays_before={n_rays_before}\n")
        fp.write(f"rays_after={len(theta_vals)}\n")
        fp.write(f"dropped_rays={n_rays_before-len(theta_vals)}\n")
        fp.write(f"marker={args.marker}\n")
        fp.write(f"width_mode={args.width_mode}\n")
        fp.write(f"median_s_peak_over_R={med_speak_R:.8g}\n")
        fp.write(f"median_delta_rho_over_R={med_delta_R:.8g}\n")
        fp.write(f"wall_exclude_R={args.wall_exclude_R:.8g}\n")
        fp.write(f"edge_guard_R={args.edge_guard_R:.8g}\n")
        fp.write(f"boundary_hit_fraction={boundary_frac:.8g}\n")
        if "marker_used" in metrics:
            vals, cnts = np.unique(metrics["marker_used"].astype(str), return_counts=True)
            for v, c in zip(vals, cnts):
                fp.write(f"marker_used_count[{v}]={int(c)}\n")
        if np.isfinite(med_speak_R) and med_speak_R < args.warn_speak_R:
            fp.write("WARNING: median s_peak/R is very small. The registration may be attached to the wall gradient, not the bow shock. Increase --wall-exclude-R or use --marker halfjump.\n")
        if np.isfinite(boundary_frac) and boundary_frac > 0.25 and args.marker == "maxgrad":
            fp.write("WARNING: many max-gradient markers are on a search-window edge. Use --marker hybrid or --marker halfjump.\n")

    cube_loaded, xwin, ywin, swin = sample_attached_snapshots(
        ref_xy, snapshots, load_variables, args.xc, args.yc, args.R,
        theta_vals, xi_vals, metrics["s_peak"], metrics["delta_rho"], args.interp,
        physical_wall_buffer_R=args.physical_wall_buffer_R
    )
    requested_indices = [load_variables.index(v) for v in requested_variables]
    cube = cube_loaded[:, requested_indices, :, :]

    X, mean_cube, rms_cube, valid_cube, meta = build_feature_matrix(cube, requested_variables, args.scale)
    nfeatures = X.shape[0]

    # Write mean and RMS fields in shock-attached window.
    mean_vars = {f"{v}_mean": mean_cube[i] for i, v in enumerate(requested_variables)}
    mean_vars.update({f"{v}_rms": rms_cube[i] for i, v in enumerate(requested_variables)})
    mean_vars.update({f"{v}_valid": valid_cube[i].astype(float) for i, v in enumerate(requested_variables)})
    write_window_field(out / "shock_window_mean_rms.dat", theta_vals, xi_vals, xwin, ywin, swin,
                       mean_vars, title="shock_window_mean_rms")

    with open(out / "shock_window_qc_summary.csv", "w", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(["quantity", "value"])
        wr.writerow(["n_snapshots", nsnap])
        wr.writerow(["n_variables", nvar])
        wr.writerow(["physical_wall_buffer_R", args.physical_wall_buffer_R])
        physical_mask = np.isfinite(swin)
        wr.writerow(["physical_window_valid_fraction", float(np.mean(physical_mask))])
        if np.any(physical_mask):
            wr.writerow(["minimum_retained_s_over_R", float(np.nanmin(swin) / args.R)])
        wr.writerow(["variables", " ".join(requested_variables)])
        wr.writerow(["ntheta", args.ntheta])
        wr.writerow(["nxi", args.nxi])
        wr.writerow(["n_features_used", nfeatures])
        wr.writerow(["feature_fraction_of_full_window", nfeatures / (nvar * len(theta_vals) * args.nxi)])
        wr.writerow(["registration", f"time_mean_density_{args.marker}_{args.width_mode}"])
        wr.writerow(["rays_before_drop", n_rays_before])
        wr.writerow(["rays_after_drop", len(theta_vals)])
        wr.writerow(["dropped_rays", n_rays_before - len(theta_vals)])
        wr.writerow(["median_s_peak_over_R", med_speak_R])
        wr.writerow(["median_delta_rho_over_R", med_delta_R])
        wr.writerow(["wall_exclude_R", args.wall_exclude_R])
        wr.writerow(["marker", args.marker])
        wr.writerow(["width_mode", args.width_mode])
        wr.writerow(["boundary_hit_fraction", boundary_frac])
        wr.writerow(["scale", args.scale])
        wr.writerow(["dt_star", args.dt_star])
        for m in meta:
            wr.writerow([f"scale_{m['var_name']}", m["scale"]])
            wr.writerow([f"valid_features_{m['var_name']}", len(m["flat_indices"])])

    # POD.
    U, S, Vh, energy, coeff = run_pod(X)
    with open(out / "pod_energy.csv", "w", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(["mode", "singular_value", "energy_fraction", "cumulative_energy"])
        cum = np.cumsum(energy)
        for i in range(len(S)):
            wr.writerow([i+1, S[i], energy[i], cum[i]])
    with open(out / "pod_coefficients.csv", "w", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(["snapshot"] + [f"a{m+1}" for m in range(min(args.n_pod_modes, coeff.shape[0]))])
        for k in range(nsnap):
            wr.writerow([k+1] + [coeff[m, k] for m in range(min(args.n_pod_modes, coeff.shape[0]))])

    nm_write = min(args.write_mode_fields, U.shape[1])
    for m in range(nm_write):
        mode_cube = vector_to_cube(U[:, m], meta, nvar, args.ntheta, args.nxi, unscale=True).real
        md = {f"{v}_pod_mode_{m+1:03d}": mode_cube[i] for i, v in enumerate(requested_variables)}
        write_window_field(out / f"POD_mode_{m+1:03d}.dat", theta_vals, xi_vals, xwin, ywin, swin,
                           md, title=f"POD_mode_{m+1:03d}")

    # DMD.
    eigvals, omega, freq, growth, Phi, b, dmd_svals = run_dmd(X, args.dt_star, args.dmd_rank)
    amp = np.abs(b)
    order = np.lexsort((-amp, -np.abs(eigvals)))  # not ideal; reverse below
    order = order[::-1]
    with open(out / "dmd_eigs.csv", "w", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(["rank_order", "eig_index", "lambda_real", "lambda_imag", "abs_lambda",
                     "omega_real_growth", "omega_imag", "frequency_cycles_per_dtstar", "amplitude_abs"])
        for rr, idx in enumerate(order, start=1):
            wr.writerow([rr, int(idx)+1, eigvals[idx].real, eigvals[idx].imag, abs(eigvals[idx]),
                         growth[idx], omega[idx].imag, freq[idx], amp[idx]])
    with open(out / "dmd_singular_values.csv", "w", newline="") as fp:
        wr = csv.writer(fp)
        wr.writerow(["index", "singular_value"])
        for i, sv in enumerate(dmd_svals, start=1):
            wr.writerow([i, sv])

    ndmd_write = min(args.write_mode_fields, len(order))
    for rr in range(ndmd_write):
        idx = order[rr]
        mode_vec = Phi[:, idx]
        mode_cube = vector_to_cube(mode_vec, meta, nvar, args.ntheta, args.nxi, unscale=True)
        for kind, arrfun in [("real", np.real), ("imag", np.imag), ("abs", np.abs)]:
            md = {f"{v}_dmd_{kind}_{rr+1:03d}": arrfun(mode_cube[i]) for i, v in enumerate(requested_variables)}
            write_window_field(out / f"DMD_mode_{rr+1:03d}_{kind}.dat", theta_vals, xi_vals, xwin, ywin, swin,
                               md, title=f"DMD_mode_{rr+1:03d}_{kind}")

    # SPOD in POD subspace.
    if args.do_spod:
        freqs, lead, total, lead_vecs, starts, nfft = run_spod_in_pod_subspace(
            coeff, U, energy, args.spod_nfft, args.spod_overlap, args.dt_star, args.spod_pod_rank
        )
        with open(out / "spod_spectrum.csv", "w", newline="") as fp:
            wr = csv.writer(fp)
            wr.writerow(["freq_cycles_per_dtstar", "leading_eigenvalue", "total_power", "leading_fraction"])
            for f0, l0, t0 in zip(freqs, lead, total):
                wr.writerow([f0, l0, t0, l0 / t0 if t0 > 0 else np.nan])
        with open(out / "spod_info.csv", "w", newline="") as fp:
            wr = csv.writer(fp)
            wr.writerow(["quantity", "value"])
            wr.writerow(["method", "POD-subspace SPOD"])
            wr.writerow(["nfft", nfft])
            wr.writerow(["n_segments", len(starts)])
            wr.writerow(["segment_starts_0based", " ".join(map(str, starts))])
            wr.writerow(["pod_rank", min(args.spod_pod_rank, coeff.shape[0])])
        # Write a few leading SPOD modes at the strongest nonzero frequencies.
        freq_order = np.argsort(lead)[::-1]
        count = 0
        for fi in freq_order:
            if freqs[fi] == 0 and len(freq_order) > 1:
                continue
            # POD basis combination in feature space
            r = min(args.spod_pod_rank, U.shape[1])
            mode_vec = U[:, :r] @ lead_vecs[fi, :r]
            mode_cube = vector_to_cube(mode_vec, meta, nvar, args.ntheta, args.nxi, unscale=True)
            md = {f"{v}_spod_abs": np.abs(mode_cube[i]) for i, v in enumerate(requested_variables)}
            fname = out / f"SPOD_lead_freqrank_{count+1:03d}_f_{freqs[fi]:.8g}_abs.dat"
            write_window_field(fname, theta_vals, xi_vals, xwin, ywin, swin, md,
                               title=f"SPOD_lead_freqrank_{count+1:03d}")
            count += 1
            if count >= args.write_mode_fields:
                break

    # Simple plots.
    try:
        import matplotlib.pyplot as plt
        cum = np.cumsum(energy)
        plt.figure()
        plt.semilogy(np.arange(1, len(energy)+1), energy, marker='o')
        plt.xlabel('POD mode')
        plt.ylabel('Energy fraction')
        plt.tight_layout()
        plt.savefig(out / 'pod_energy_fraction.png', dpi=200)
        plt.close()

        plt.figure()
        plt.plot(np.arange(1, len(cum)+1), cum, marker='o')
        plt.xlabel('POD mode')
        plt.ylabel('Cumulative energy')
        plt.ylim(0, 1.01)
        plt.tight_layout()
        plt.savefig(out / 'pod_cumulative_energy.png', dpi=200)
        plt.close()

        plt.figure()
        plt.scatter(eigvals.real, eigvals.imag)
        th = np.linspace(0, 2*np.pi, 400)
        plt.plot(np.cos(th), np.sin(th))
        plt.xlabel('Re(lambda)')
        plt.ylabel('Im(lambda)')
        plt.axis('equal')
        plt.tight_layout()
        plt.savefig(out / 'dmd_spectrum.png', dpi=200)
        plt.close()

        if args.do_spod:
            plt.figure()
            plt.semilogy(freqs, lead, marker='o')
            plt.xlabel('Frequency [cycles/dt*]')
            plt.ylabel('Leading SPOD eigenvalue')
            plt.tight_layout()
            plt.savefig(out / 'spod_leading_spectrum.png', dpi=200)
            plt.close()
    except Exception as e:
        with open(out / "plot_warning.txt", "w") as fp:
            fp.write(str(e))

    print("Done.")
    print(f"Snapshots: {nsnap}")
    print(f"Shock-window features used: {nfeatures} / {nvar * len(theta_vals) * args.nxi}")
    print(f"Rays kept: {len(theta_vals)} / {n_rays_before}; median s_peak/R={med_speak_R:.4g}")
    print(f"Output directory: {out}")
    print("Key files: shock_window_mean_rms.dat, pod_energy.csv, dmd_eigs.csv, shock_window_qc_summary.csv")


if __name__ == "__main__":
    main()
