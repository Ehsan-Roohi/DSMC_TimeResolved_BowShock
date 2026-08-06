#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.ndimage import gaussian_filter1d, uniform_filter1d
from scipy.optimize import nnls
from scipy.spatial import cKDTree

from ds2ff_io_reference import (
    natural_key,
    read_tecplot_point_file,
    validate_or_remap_to_reference,
)


def crossing(s: np.ndarray, q: np.ndarray, level: float, mask: np.ndarray) -> float:
    ids = np.where(mask & np.isfinite(q))[0]
    if ids.size < 2:
        return np.nan
    for a, b in zip(ids[:-1], ids[1:]):
        qa = q[a] - level
        qb = q[b] - level
        if qa == 0:
            return float(s[a])
        if qa * qb < 0 and qb != qa:
            return float(s[a] + (level - q[a]) * (s[b] - s[a]) / (q[b] - q[a]))
    return np.nan


def one_profile_marker(
    s: np.ndarray,
    profile: np.ndarray,
    wall_exclude_R: float,
    R: float,
    smooth_sigma: float,
    search_far_fraction: float,
) -> tuple[float, float, float, float]:
    valid = np.isfinite(profile)
    if valid.sum() < 30:
        return np.nan, np.nan, np.nan, np.nan

    ids = np.where(valid)[0]
    cuts = np.where(np.diff(ids) > 1)[0]
    starts = np.r_[0, cuts + 1]
    ends = np.r_[cuts, len(ids) - 1]
    longest = int(np.argmax(ends - starts + 1))
    ii = ids[starts[longest] : ends[longest] + 1]

    ss = s[ii]
    pp = profile[ii]
    if ss.size < 30:
        return np.nan, np.nan, np.nan, np.nan

    ps = (
        gaussian_filter1d(pp, sigma=smooth_sigma, mode="nearest")
        if smooth_sigma > 0
        else pp
    )
    slen = ss[-1] - ss[0]
    search = (
        (ss >= wall_exclude_R * R)
        & (ss <= ss[0] + search_far_fraction * slen)
    )
    if search.sum() < 8:
        return np.nan, np.nan, np.nan, np.nan

    smin = float(np.min(ss[search]))
    smax = float(np.max(ss[search]))
    downstream = (ss >= smin) & (ss <= min(smax, smin + 0.20 * R))
    upstream = ss >= ss[0] + 0.85 * slen
    if downstream.sum() < 5 or upstream.sum() < 5:
        return np.nan, np.nan, np.nan, np.nan

    rho_down = float(np.nanmedian(ps[downstream]))
    rho_up = float(np.nanmedian(ps[upstream]))
    jump = rho_down - rho_up
    if not np.isfinite(jump) or abs(jump) < 1.0e-300:
        return np.nan, np.nan, np.nan, np.nan

    q = (ps - rho_up) / jump
    s10 = crossing(ss, q, 0.10, search)
    s50 = crossing(ss, q, 0.50, search)
    s90 = crossing(ss, q, 0.90, search)
    width = abs(s90 - s10) if np.isfinite(s10) and np.isfinite(s90) else np.nan
    return s50, width, rho_down, rho_up


def fill_temporal_nans(X: np.ndarray, minimum_valid_fraction: float = 0.75):
    X = np.asarray(X, dtype=float).copy()
    valid_fraction = np.mean(np.isfinite(X), axis=0)
    keep = valid_fraction >= minimum_valid_fraction
    X = X[:, keep]
    if X.size == 0:
        return X, keep

    index = np.arange(X.shape[0])
    for j in range(X.shape[1]):
        good = np.isfinite(X[:, j])
        if good.sum() < 2:
            X[:, j] = np.nan
        elif not good.all():
            X[~good, j] = np.interp(index[~good], index[good], X[good, j])

    complete = np.all(np.isfinite(X), axis=0)
    retained = np.where(keep)[0][complete]
    final_keep = np.zeros_like(keep, dtype=bool)
    final_keep[retained] = True
    return X[:, complete], final_keep


def angular_correlation_length(theta_deg: np.ndarray, X: np.ndarray):
    Xc = X - np.mean(X, axis=0, keepdims=True)
    C = Xc.T @ Xc / max(1, Xc.shape[0] - 1)
    d = np.sqrt(np.maximum(np.diag(C), 0))
    Rcorr = C / np.maximum(d[:, None] * d[None, :], 1.0e-300)

    sep = []
    corr = []
    for i in range(len(theta_deg)):
        for j in range(i + 1, len(theta_deg)):
            if np.isfinite(Rcorr[i, j]):
                sep.append(abs(theta_deg[j] - theta_deg[i]))
                corr.append(Rcorr[i, j])
    sep = np.asarray(sep)
    corr = np.asarray(corr)
    if sep.size == 0:
        return np.nan, np.empty(0), np.empty(0)

    bins = np.linspace(0, float(np.max(sep)) + 1.0e-12, 21)
    centers = 0.5 * (bins[:-1] + bins[1:])
    mean_corr = np.full_like(centers, np.nan)
    for k in range(len(centers)):
        mask = (sep >= bins[k]) & (sep < bins[k + 1])
        if np.any(mask):
            mean_corr[k] = float(np.mean(corr[mask]))

    good = np.isfinite(mean_corr)
    positive = np.where(good, np.maximum(mean_corr, 0), 0)
    length = (
        float(np.trapezoid(positive, centers))
        if np.count_nonzero(good) > 1
        else np.nan
    )
    return length, centers, mean_corr


def marker_metrics(theta_deg: np.ndarray, marker: np.ndarray):
    X, keep = fill_temporal_nans(marker)
    theta = theta_deg[keep]
    if X.shape[0] < 3 or X.shape[1] < 3:
        return None

    Xc = X - np.mean(X, axis=0, keepdims=True)
    U, S, Vt = np.linalg.svd(Xc, full_matrices=False)
    energy = S * S
    energy_fraction = energy / energy.sum() if energy.sum() > 0 else np.full_like(energy, np.nan)
    mode1 = Vt[0]
    mode1 = mode1 / np.linalg.norm(mode1)

    participation = float(1.0 / np.sum(mode1**4))
    mode_energy = mode1 * mode1

    if theta.size > 1:
        dtheta = float(np.median(np.diff(theta)))
        sector_n = max(1, int(round(10.0 / max(dtheta, 1.0e-12))))
    else:
        sector_n = 1
    sector_n = min(sector_n, len(mode_energy))
    max_sector = max(
        float(np.sum(mode_energy[i : i + sector_n]))
        for i in range(len(mode_energy) - sector_n + 1)
    )

    uniform = np.ones(len(mode1)) / np.sqrt(len(mode1))
    tilt = theta - np.mean(theta)
    tilt = tilt / np.linalg.norm(tilt) if np.linalg.norm(tilt) > 0 else tilt

    point_variance = np.var(X, axis=0, ddof=1)
    global_series = np.mean(Xc, axis=1)
    mean_point_variance = float(np.mean(point_variance))
    global_fraction = (
        float(np.var(global_series, ddof=1) / mean_point_variance)
        if mean_point_variance > 0
        else np.nan
    )
    corr_length, sep, corr = angular_correlation_length(theta, X)

    return {
        "n_groups": int(X.shape[0]),
        "n_rays_retained": int(X.shape[1]),
        "mean_marker": float(np.mean(X)),
        "mean_point_std": float(np.mean(np.std(X, axis=0, ddof=1))),
        "mean_point_variance": mean_point_variance,
        "global_series_std": float(np.std(global_series, ddof=1)),
        "angular_POD_E1": float(energy_fraction[0]),
        "uniform_mode_correlation": abs(float(np.dot(mode1, uniform))),
        "tilt_mode_correlation": abs(float(np.dot(mode1, tilt))),
        "global_coherent_variance_fraction": global_fraction,
        "angular_correlation_length_deg": corr_length,
        "participation_rays": participation,
        "max_10deg_mode_energy_fraction": max_sector,
        "theta_retained": theta,
        "mode1": mode1,
        "separation_deg": sep,
        "mean_angular_correlation": corr,
    }


def fit_noise_floor(group_sizes: np.ndarray, variances: np.ndarray):
    mask = (
        np.isfinite(group_sizes)
        & np.isfinite(variances)
        & (group_sizes > 0)
        & (variances >= 0)
    )
    m = group_sizes[mask].astype(float)
    y = variances[mask].astype(float)
    if m.size < 3:
        return None

    A = np.column_stack([np.ones_like(m), 1.0 / m])
    coeff, _ = nnls(A, y)
    physical_var, sampling_var_m1 = map(float, coeff)
    pred = A @ coeff
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan
    total_m1 = physical_var + sampling_var_m1
    return {
        "physical_variance_floor": physical_var,
        "sampling_variance_at_m1": sampling_var_m1,
        "physical_fraction_at_m1": (
            physical_var / total_m1 if total_m1 > 0 else np.nan
        ),
        "sampling_fraction_at_m1": (
            sampling_var_m1 / total_m1 if total_m1 > 0 else np.nan
        ),
        "fit_R2": r2,
    }


def self_test():
    rng = np.random.default_rng(12)
    theta = np.linspace(120, 179, 60)
    n = 256
    physical = 0.002 * np.sin(np.arange(n)[:, None] / 13.0) * np.ones((1, 60))
    local_shape = np.exp(-0.5 * ((theta - 150) / 4.0) ** 2)
    local = 0.001 * np.sin(np.arange(n)[:, None] / 7.0) * local_shape[None, :]
    noise = 0.004 * rng.standard_normal((n, 60))
    X = physical + local + noise

    sizes = np.array([1, 2, 4, 8, 16])
    variances = []
    for m in sizes:
        ng = n // m
        Y = X[: ng * m].reshape(ng, m, 60).mean(axis=1)
        metrics = marker_metrics(theta, Y)
        assert metrics is not None
        variances.append(metrics["mean_point_variance"])
    fit = fit_noise_floor(sizes, np.asarray(variances))
    assert fit is not None
    assert 0 <= fit["physical_fraction_at_m1"] <= 1
    assert fit["fit_R2"] > 0.8
    print("SELF-TEST PASS")


def main():
    ap = argparse.ArgumentParser(
        description="Temporal coarse-graining of existing DS2FF snapshots before marker extraction."
    )
    ap.add_argument("--pattern")
    ap.add_argument("--out")
    ap.add_argument("--dt-star", type=float)
    ap.add_argument("--group-sizes", nargs="+", type=int, default=[1, 2, 4, 8, 16])
    ap.add_argument("--count", type=int, default=200)
    ap.add_argument("--start-index", type=int, default=0)
    ap.add_argument("--zone", type=int, default=1)
    ap.add_argument("--xc", type=float, default=0.1524)
    ap.add_argument("--yc", type=float, default=0.0)
    ap.add_argument("--R", type=float, default=0.1524)
    ap.add_argument("--theta-min", type=float, default=120.0)
    ap.add_argument("--theta-max", type=float, default=179.0)
    ap.add_argument("--ntheta", type=int, default=60)
    ap.add_argument("--nr-raw", type=int, default=900)
    ap.add_argument("--smax-R", type=float, default=8.0)
    ap.add_argument("--wall-exclude-R", type=float, default=0.25)
    ap.add_argument("--smooth-sigma", type=float, default=4.0)
    ap.add_argument("--search-far-fraction", type=float, default=0.94)
    ap.add_argument(
        "--theta-smooth-rays",
        nargs="+",
        type=int,
        default=[1, 3, 5],
        help="Odd-width angular smoothing kernels applied to the block-averaged density ray profiles.",
    )
    ap.add_argument("--input-remap", choices=["none", "nearest"], default="nearest")
    ap.add_argument("--grid-tol", type=float, default=1.0e-10)
    ap.add_argument("--coord-match-tol", type=float, default=1.0e-8)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return

    if not args.pattern or not args.out or args.dt_star is None:
        ap.error("--pattern, --out and --dt-star are required unless --self-test is used.")

    group_sizes = sorted(set(int(x) for x in args.group_sizes if int(x) > 0))
    theta_smooth = sorted(set(int(x) for x in args.theta_smooth_rays if int(x) > 0))
    for w in theta_smooth:
        if w % 2 == 0:
            raise ValueError("--theta-smooth-rays values must be odd positive integers.")

    files = sorted(glob.glob(args.pattern), key=natural_key)[args.start_index :]
    if args.count > 0:
        files = files[: args.count]
    if len(files) < max(group_sizes) * 2:
        raise SystemExit(
            f"Need at least {max(group_sizes)*2} snapshots; found {len(files)}."
        )

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    vars0, zones0 = read_tecplot_point_file(files[0])
    zi = args.zone - 1
    if zi < 0 or zi >= len(zones0):
        raise ValueError(f"Requested zone {args.zone}; file contains {len(zones0)} zones.")
    for name in ["X", "Y", "D"]:
        if name not in vars0:
            raise ValueError(f"Missing variable {name}; available={vars0}")
    xidx, yidx, didx = [vars0.index(v) for v in ["X", "Y", "D"]]
    ref_zones = zones0
    ref_xy = zones0[zi].data[:, [xidx, yidx]]
    npoint = ref_xy.shape[0]

    theta = np.linspace(args.theta_min, args.theta_max, args.ntheta)
    s = np.linspace(0.0, args.smax_R * args.R, args.nr_raw)
    xray = args.xc + np.cos(np.deg2rad(theta))[:, None] * (args.R + s[None, :])
    yray = args.yc + np.sin(np.deg2rad(theta))[:, None] * (args.R + s[None, :])
    ray_points = np.column_stack([xray.ravel(), yray.ravel()])
    tree = cKDTree(ref_xy)
    _, nearest = tree.query(ray_points, k=1)
    nearest = nearest.reshape(args.ntheta, args.nr_raw)

    # Load once per case as float32 to avoid repeated disk reads.
    density = np.empty((len(files), npoint), dtype=np.float32)
    alignment_rows = []
    for it, file in enumerate(files):
        vars_i, zones_i = read_tecplot_point_file(file)
        if vars_i != vars0:
            raise ValueError(f"Variable mismatch in {file}")
        aligned, info = validate_or_remap_to_reference(
            file,
            zones_i,
            ref_zones,
            zi,
            [didx],
            (xidx, yidx),
            args.grid_tol,
            args.coord_match_tol,
            args.input_remap,
        )
        density[it] = aligned[:, 0].astype(np.float32, copy=False)
        alignment_rows.append(info)
        print(f"LOAD {it+1}/{len(files)} {Path(file).name}")

    pd.DataFrame(alignment_rows).to_csv(out / "snapshot_alignment_qc.csv", index=False)

    summary_rows = []
    long_rows = []
    fit_input_rows = []

    for m in group_sizes:
        n_groups = len(files) // m
        used = n_groups * m
        block_density = density[:used].reshape(n_groups, m, npoint).mean(axis=1)

        for angular_width in theta_smooth:
            marker = np.full((n_groups, args.ntheta), np.nan)
            width = np.full_like(marker, np.nan)

            for ig in range(n_groups):
                profiles = block_density[ig, nearest]
                if angular_width > 1:
                    profiles = uniform_filter1d(
                        profiles,
                        size=angular_width,
                        axis=0,
                        mode="nearest",
                    )

                for j in range(args.ntheta):
                    s50, delta, rho_down, rho_up = one_profile_marker(
                        s,
                        profiles[j],
                        args.wall_exclude_R,
                        args.R,
                        args.smooth_sigma,
                        args.search_far_fraction,
                    )
                    marker[ig, j] = s50 / args.R if np.isfinite(s50) else np.nan
                    width[ig, j] = delta / args.R if np.isfinite(delta) else np.nan
                    long_rows.append(
                        {
                            "group_size": m,
                            "angular_smoothing_rays": angular_width,
                            "group": ig + 1,
                            "group_time_center_star": (
                                (ig * m + 0.5 * (m - 1)) * args.dt_star
                            ),
                            "theta_deg": theta[j],
                            "s50_over_R": marker[ig, j],
                            "delta_over_R": width[ig, j],
                            "rho_down": rho_down,
                            "rho_up": rho_up,
                        }
                    )

            for quantity, matrix in [("center", marker), ("width", width)]:
                metrics = marker_metrics(theta, matrix)
                if metrics is None:
                    continue
                row = {
                    "quantity": quantity,
                    "group_size": m,
                    "angular_smoothing_rays": angular_width,
                    "effective_dt_star": m * args.dt_star,
                    "raw_snapshots_used": used,
                    "marker_valid_fraction": float(np.mean(np.isfinite(matrix))),
                }
                for key, value in metrics.items():
                    if isinstance(value, (float, int, np.floating, np.integer)):
                        row[key] = value
                summary_rows.append(row)
                fit_input_rows.append(
                    {
                        "quantity": quantity,
                        "angular_smoothing_rays": angular_width,
                        "group_size": m,
                        "mean_point_variance": metrics["mean_point_variance"],
                        "global_series_variance": metrics["global_series_std"] ** 2,
                    }
                )

                tag = f"{quantity}_m{m}_ang{angular_width}"
                pd.DataFrame(
                    {
                        "theta_deg": metrics["theta_retained"],
                        "mode1": metrics["mode1"],
                    }
                ).to_csv(out / f"mode1_{tag}.csv", index=False)
                pd.DataFrame(
                    {
                        "separation_deg": metrics["separation_deg"],
                        "mean_correlation": metrics["mean_angular_correlation"],
                    }
                ).to_csv(out / f"angular_correlation_{tag}.csv", index=False)

            np.savez_compressed(
                out / f"marker_arrays_m{m}_ang{angular_width}.npz",
                theta_deg=theta,
                group_time_center_star=(
                    np.arange(n_groups) * m + 0.5 * (m - 1)
                )
                * args.dt_star,
                s50_over_R=marker,
                delta_over_R=width,
            )
            print(
                f"DONE m={m}, angular smoothing={angular_width}, groups={n_groups}"
            )

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(out / "coarse_graining_summary.csv", index=False)
    pd.DataFrame(long_rows).to_csv(out / "coarse_graining_marker_long.csv", index=False)

    fit_df = pd.DataFrame(fit_input_rows)
    fit_rows = []
    for (quantity, angular_width), g in fit_df.groupby(
        ["quantity", "angular_smoothing_rays"]
    ):
        for variance_name in ["mean_point_variance", "global_series_variance"]:
            fit = fit_noise_floor(
                g["group_size"].to_numpy(),
                g[variance_name].to_numpy(),
            )
            if fit is None:
                continue
            fit_rows.append(
                {
                    "quantity": quantity,
                    "angular_smoothing_rays": angular_width,
                    "variance_metric": variance_name,
                    **fit,
                }
            )
    pd.DataFrame(fit_rows).to_csv(out / "noise_floor_fits.csv", index=False)

    metadata = {
        "n_input_snapshots": len(files),
        "dt_star": args.dt_star,
        "group_sizes": group_sizes,
        "theta_smooth_rays": theta_smooth,
        "theta_range_deg": [args.theta_min, args.theta_max],
        "wall_exclude_R": args.wall_exclude_R,
        "smax_R": args.smax_R,
        "interpretation": (
            "Variance is fitted as sigma^2(m)=sigma_phys^2+sigma_sampling^2/m. "
            "A positive plateau supports physical fluctuations; 1/m scaling supports sampling noise."
        ),
    }
    (out / "coarse_graining_metadata.json").write_text(
        json.dumps(metadata, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
