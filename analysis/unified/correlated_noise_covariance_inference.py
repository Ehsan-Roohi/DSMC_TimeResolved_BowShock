#!/usr/bin/env python3
"""Correlated-noise covariance inference for shock-layer marker dynamics.

This script uses the existing temporal-coarse-graining marker arrays.  It does
not run DSMC and does not re-extract markers from raw DS2FF fields.

For each Kn case and angular-smoothing setting, it fits

    C_m = A_m(phi_p) C_p + A_m(phi_n) C_n,

where C_m is the angular covariance of a marker measured after averaging m
consecutive snapshots, C_p is a physical covariance, C_n is a sampling-noise
covariance, and A_m(phi) is the exact attenuation factor for block averages of
an AR(1) process.

The sampling correlation phi_n is calibrated from the width channel.  The
physical correlation phi_p is inferred from centre-variance scaling and the
m=1 centre autocorrelation.  Full covariance matrices are then decomposed with
positive-semidefinite constraints.  The code also performs aligned moving-block
bootstrap, far-angle covariance tests, stationarity checks, leave-one-m-out
model comparison, and matched synthetic positive/negative controls.
"""
from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import nnls
from scipy.stats import levene, linregress

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

def case_name_to_kn(name: str) -> float:
    """Parse labels such as Kn0p025, Kn0p10, Kn1p00."""
    match = re.fullmatch(r"Kn(\d+)p(\d+)", name)
    if not match:
        return float("nan")
    return float(f"{int(match.group(1))}.{match.group(2)}")


@dataclass
class FitOptions:
    max_acf_lag: int = 8
    acf_weight_noise: float = 1.0
    acf_weight_physical: float = 1.0
    phi_grid_size: int = 500
    phi_min: float = -0.25
    phi_max: float = 0.995
    psd_iterations: int = 250
    psd_tolerance: float = 1.0e-9
    far_angle_deg: float = 15.0
    bootstrap_replicates: int = 200
    control_replicates: int = 40
    random_seed: int = 12031


@dataclass
class ChannelData:
    theta_deg: np.ndarray
    group_sizes: List[int]
    arrays: Dict[int, np.ndarray]
    dt_star: float


@dataclass
class ScalarFit:
    phi_noise: float
    phi_physical: float
    tau_noise_exponential_star: float
    tau_physical_exponential_star: float
    tau_noise_integral_star: float
    tau_physical_integral_star: float
    trace_physical: float
    trace_noise: float
    global_physical: float
    global_noise: float
    objective_noise_only: float
    objective_two_component: float
    aicc_noise_only: float
    aicc_two_component: float
    delta_aicc: float
    width_fit_r2_trace: float
    width_fit_r2_global: float
    centre_fit_r2_trace: float
    centre_fit_r2_global: float
    acf_fit_rmse_noise: float
    acf_fit_rmse_centre: float
    design_condition_number: float


@dataclass
class CovarianceFit:
    C_physical: np.ndarray
    C_noise: np.ndarray
    C_physical_raw: np.ndarray
    C_noise_raw: np.ndarray
    raw_negative_mass_physical: float
    raw_negative_mass_noise: float
    raw_negative_fraction_physical: float
    raw_negative_fraction_noise: float
    projected_relative_correction_physical: float
    projected_relative_correction_noise: float
    weighted_relative_residual: float
    iterations: int
    loocv_error_two_component: float
    loocv_error_noise_only: float


# ---------------------------------------------------------------------------
# Input and preprocessing
# ---------------------------------------------------------------------------

def parse_group_size(path: Path) -> int:
    match = re.search(r"_m(\d+)_ang", path.stem)
    if not match:
        raise ValueError(f"Cannot parse group size from {path.name}")
    return int(match.group(1))


def fill_temporal_nans(X: np.ndarray, min_valid_fraction: float = 0.75) -> Tuple[np.ndarray, np.ndarray]:
    X = np.asarray(X, dtype=float).copy()
    if X.ndim != 2:
        raise ValueError("Marker array must be two-dimensional [time, ray].")
    keep = np.mean(np.isfinite(X), axis=0) >= min_valid_fraction
    X = X[:, keep]
    t = np.arange(X.shape[0])
    for j in range(X.shape[1]):
        good = np.isfinite(X[:, j])
        if good.sum() < 2:
            X[:, j] = np.nan
        elif not good.all():
            X[~good, j] = np.interp(t[~good], t[good], X[good, j])
    complete = np.all(np.isfinite(X), axis=0)
    retained = np.where(keep)[0][complete]
    final_keep = np.zeros_like(keep, dtype=bool)
    final_keep[retained] = True
    return X[:, complete], final_keep


def load_case_channels(case_dir: Path, angular_smoothing: int, min_valid_fraction: float = 0.75) -> Tuple[ChannelData, ChannelData]:
    records: Dict[int, Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}
    for npz_path in sorted(case_dir.glob(f"marker_arrays_m*_ang{angular_smoothing}.npz")):
        m = parse_group_size(npz_path)
        z = np.load(npz_path)
        theta = np.asarray(z["theta_deg"], dtype=float)
        time = np.asarray(z["group_time_center_star"], dtype=float)
        centre = np.asarray(z["s50_over_R"], dtype=float)
        width = np.asarray(z["delta_over_R"], dtype=float)
        records[m] = (theta, time, centre, width)
    if not records:
        raise FileNotFoundError(
            f"No marker_arrays_m*_ang{angular_smoothing}.npz in {case_dir}"
        )
    if 1 not in records:
        raise ValueError("Group size m=1 is required.")

    group_sizes = sorted(records)
    base_theta = records[1][0]
    if len(base_theta) < 4:
        raise ValueError("Too few angular rays.")

    # Retain one common set of rays across centre/width and every m.
    common_keep = np.ones(len(base_theta), dtype=bool)
    for m in group_sizes:
        theta, _, centre, width = records[m]
        if len(theta) != len(base_theta) or not np.allclose(theta, base_theta):
            raise ValueError(f"Theta grid mismatch at m={m} in {case_dir}")
        common_keep &= np.mean(np.isfinite(centre), axis=0) >= min_valid_fraction
        common_keep &= np.mean(np.isfinite(width), axis=0) >= min_valid_fraction
    if common_keep.sum() < 4:
        raise ValueError("Fewer than four rays remain after common validity filtering.")

    centre_arrays: Dict[int, np.ndarray] = {}
    width_arrays: Dict[int, np.ndarray] = {}
    for m in group_sizes:
        _, _, centre, width = records[m]
        centre = centre[:, common_keep]
        width = width[:, common_keep]
        centre, centre_keep = fill_temporal_nans(centre, min_valid_fraction=0.0)
        width, width_keep = fill_temporal_nans(width, min_valid_fraction=0.0)
        if not np.all(centre_keep) or not np.all(width_keep):
            raise ValueError(f"Unexpected post-filter ray loss at m={m}")
        centre_arrays[m] = centre
        width_arrays[m] = width

    time1 = records[1][1]
    dt_star = float(np.median(np.diff(time1))) if len(time1) > 1 else 1.0
    theta = base_theta[common_keep]
    return (
        ChannelData(theta, group_sizes, centre_arrays, dt_star),
        ChannelData(theta, group_sizes, width_arrays, dt_star),
    )


# ---------------------------------------------------------------------------
# Time-series/covariance utilities
# ---------------------------------------------------------------------------

def demean(X: np.ndarray) -> np.ndarray:
    return X - np.mean(X, axis=0, keepdims=True)


def covariance(X: np.ndarray) -> np.ndarray:
    Xc = demean(np.asarray(X, dtype=float))
    return Xc.T @ Xc / max(1, len(Xc) - 1)


def global_mean_variance(C: np.ndarray) -> float:
    n = C.shape[0]
    one = np.ones(n) / n
    return float(one @ C @ one)


def trace_mean_variance(C: np.ndarray) -> float:
    return float(np.trace(C) / C.shape[0])


def acf_fft(x: np.ndarray, max_lag: int | None = None) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 4:
        return np.full(1, np.nan)
    x = x - np.mean(x)
    n = len(x)
    nfft = 1 << (2 * n - 1).bit_length()
    f = np.fft.rfft(x, n=nfft)
    ac = np.fft.irfft(f * np.conjugate(f), n=nfft)[:n]
    ac /= np.arange(n, 0, -1, dtype=float)
    ac = ac / ac[0] if ac[0] > 0 else np.full(n, np.nan)
    if max_lag is not None:
        ac = ac[: max_lag + 1]
    return ac


def mean_ray_acf(X: np.ndarray, max_lag: int) -> np.ndarray:
    acfs = []
    for j in range(X.shape[1]):
        ac = acf_fft(X[:, j], max_lag=max_lag)
        if len(ac) == max_lag + 1 and np.all(np.isfinite(ac)):
            acfs.append(ac)
    return np.mean(acfs, axis=0) if acfs else np.full(max_lag + 1, np.nan)


def attenuation_ar1(m: int | np.ndarray, phi: float) -> np.ndarray:
    ms = np.atleast_1d(m).astype(int)
    out = np.empty(len(ms), dtype=float)
    for i, mm in enumerate(ms):
        if mm <= 0:
            raise ValueError("Group sizes must be positive.")
        if mm == 1:
            out[i] = 1.0
        else:
            k = np.arange(1, mm, dtype=float)
            out[i] = (
                mm + 2.0 * np.sum((mm - k) * np.power(phi, k))
            ) / (mm * mm)
    return out


def tau_exponential_from_phi(phi: float, dt_star: float) -> float:
    """Exponential e-folding time for a positive AR(1) coefficient."""
    if not (0.0 < phi < 1.0):
        return np.nan
    return float(-dt_star / np.log(phi))


def tau_integral_from_phi(phi: float, dt_star: float) -> float:
    """Discrete integral timescale for AR(1), valid for -1 < phi < 1."""
    if not (-1.0 < phi < 1.0):
        return np.nan
    return float(dt_star * (1.0 + phi) / (2.0 * (1.0 - phi)))


def covariance_series(channel: ChannelData) -> Tuple[List[np.ndarray], np.ndarray, np.ndarray, np.ndarray]:
    covariances = [covariance(channel.arrays[m]) for m in channel.group_sizes]
    trace = np.array([trace_mean_variance(C) for C in covariances])
    global_var = np.array([global_mean_variance(C) for C in covariances])
    n_groups = np.array([len(channel.arrays[m]) for m in channel.group_sizes], dtype=float)
    return covariances, trace, global_var, n_groups


def r2_score(y: np.ndarray, pred: np.ndarray) -> float:
    y = np.asarray(y, dtype=float)
    pred = np.asarray(pred, dtype=float)
    ss_res = float(np.sum((y - pred) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else np.nan


def normalized_sse(y: np.ndarray, pred: np.ndarray, weights: np.ndarray) -> float:
    scale = max(float(np.mean(y * y)), 1.0e-300)
    return float(np.sum(weights * (y - pred) ** 2) / (np.sum(weights) * scale))


def aicc(objective: float, n_obs: int, n_params: int) -> float:
    rss = max(objective * n_obs, 1.0e-300)
    value = n_obs * np.log(rss / n_obs) + 2.0 * n_params
    denom = n_obs - n_params - 1
    if denom > 0:
        value += 2.0 * n_params * (n_params + 1) / denom
    return float(value)


# ---------------------------------------------------------------------------
# Scalar AR(1)-mixture inference
# ---------------------------------------------------------------------------

def fit_single_component(
    group_sizes: Sequence[int],
    trace: np.ndarray,
    global_var: np.ndarray,
    n_groups: np.ndarray,
    acf_global: np.ndarray,
    acf_mean_ray: np.ndarray,
    options: FitOptions,
) -> Dict[str, float | np.ndarray]:
    ms = np.asarray(group_sizes, dtype=int)
    weights = np.maximum(n_groups - 1.0, 1.0)
    phi_grid = np.linspace(options.phi_min, options.phi_max, options.phi_grid_size)
    best: Dict[str, float | np.ndarray] | None = None
    lag = np.arange(1, min(options.max_acf_lag, len(acf_global) - 1) + 1)
    lag_weights = 1.0 / np.maximum(lag, 1)

    profile_rows = []
    for phi in phi_grid:
        a = attenuation_ar1(ms, phi)
        denom = float(np.sum(weights * a * a))
        amp_t = max(0.0, float(np.sum(weights * a * trace) / max(denom, 1e-300)))
        amp_g = max(0.0, float(np.sum(weights * a * global_var) / max(denom, 1e-300)))
        pred_t = amp_t * a
        pred_g = amp_g * a
        obj = normalized_sse(trace, pred_t, weights) + normalized_sse(global_var, pred_g, weights)

        acf_pred = np.power(phi, lag)
        acf_terms = []
        for observed in (acf_global, acf_mean_ray):
            obs = observed[lag]
            good = np.isfinite(obs)
            if np.any(good):
                acf_terms.append(
                    float(
                        np.sum(lag_weights[good] * (obs[good] - acf_pred[good]) ** 2)
                        / np.sum(lag_weights[good])
                    )
                )
        acf_rmse = float(np.sqrt(np.mean(acf_terms))) if acf_terms else np.nan
        if acf_terms:
            obj += options.acf_weight_noise * float(np.mean(acf_terms))
        row = {
            "phi": float(phi),
            "amplitude_trace": amp_t,
            "amplitude_global": amp_g,
            "objective": float(obj),
            "acf_rmse": acf_rmse,
            "r2_trace": r2_score(trace, pred_t),
            "r2_global": r2_score(global_var, pred_g),
            "prediction_trace": pred_t,
            "prediction_global": pred_g,
        }
        profile_rows.append(row)
        if best is None or float(row["objective"]) < float(best["objective"]):
            best = row
    assert best is not None
    best["profile"] = profile_rows
    return best


def fit_two_component(
    group_sizes: Sequence[int],
    trace: np.ndarray,
    global_var: np.ndarray,
    n_groups: np.ndarray,
    acf_global: np.ndarray,
    phi_noise: float,
    options: FitOptions,
) -> Dict[str, float | np.ndarray]:
    ms = np.asarray(group_sizes, dtype=int)
    weights = np.maximum(n_groups - 1.0, 1.0)
    sqrtw = np.sqrt(weights)
    a_noise = attenuation_ar1(ms, phi_noise)
    phi_grid = np.linspace(options.phi_min, options.phi_max, options.phi_grid_size)
    lag = np.arange(1, min(options.max_acf_lag, len(acf_global) - 1) + 1)
    lag_weights = 1.0 / np.maximum(lag, 1)

    profile_rows = []
    best: Dict[str, float | np.ndarray] | None = None
    for phi_p in phi_grid:
        a_phys = attenuation_ar1(ms, phi_p)
        design = np.column_stack([a_phys, a_noise])
        weighted_design = sqrtw[:, None] * design
        coeff_t, _ = nnls(weighted_design, sqrtw * trace)
        coeff_g, _ = nnls(weighted_design, sqrtw * global_var)
        pred_t = design @ coeff_t
        pred_g = design @ coeff_g
        obj = normalized_sse(trace, pred_t, weights) + normalized_sse(global_var, pred_g, weights)

        obs = acf_global[lag]
        good = np.isfinite(obs)
        if np.any(good):
            pg, ng = coeff_g
            denom = pg + ng
            pred_acf = (
                (pg * np.power(phi_p, lag) + ng * np.power(phi_noise, lag)) / denom
                if denom > 0
                else np.zeros_like(lag, dtype=float)
            )
            acf_mse = float(
                np.sum(lag_weights[good] * (obs[good] - pred_acf[good]) ** 2)
                / np.sum(lag_weights[good])
            )
            obj += options.acf_weight_physical * acf_mse
            acf_rmse = float(np.sqrt(acf_mse))
        else:
            pred_acf = np.full_like(lag, np.nan, dtype=float)
            acf_rmse = np.nan

        cond = float(np.linalg.cond(weighted_design))
        row = {
            "phi_physical": float(phi_p),
            "trace_physical": float(coeff_t[0]),
            "trace_noise": float(coeff_t[1]),
            "global_physical": float(coeff_g[0]),
            "global_noise": float(coeff_g[1]),
            "prediction_trace": pred_t,
            "prediction_global": pred_g,
            "prediction_acf": pred_acf,
            "objective": float(obj),
            "acf_rmse": acf_rmse,
            "r2_trace": r2_score(trace, pred_t),
            "r2_global": r2_score(global_var, pred_g),
            "condition_number": cond,
        }
        profile_rows.append(row)
        if best is None or float(row["objective"]) < float(best["objective"]):
            best = row
    assert best is not None
    best["profile"] = profile_rows
    return best


def infer_scalar_model(centre: ChannelData, width: ChannelData, options: FitOptions) -> Tuple[ScalarFit, Dict[str, object]]:
    _, wt, wg, wn = covariance_series(width)
    _, ct, cg, cn = covariance_series(centre)
    width_m1 = width.arrays[1]
    centre_m1 = centre.arrays[1]
    acf_width_global = acf_fft(np.mean(width_m1, axis=1), options.max_acf_lag)
    acf_width_rays = mean_ray_acf(width_m1, options.max_acf_lag)
    acf_centre_global = acf_fft(np.mean(centre_m1, axis=1), options.max_acf_lag)

    width_fit = fit_single_component(
        width.group_sizes, wt, wg, wn,
        acf_width_global, acf_width_rays, options,
    )
    phi_n = float(width_fit["phi"])
    centre_fit = fit_two_component(
        centre.group_sizes, ct, cg, cn,
        acf_centre_global, phi_n, options,
    )

    # Centre noise-only comparison with fixed phi_n.
    ms = np.asarray(centre.group_sizes, dtype=int)
    weights = np.maximum(cn - 1.0, 1.0)
    a_n = attenuation_ar1(ms, phi_n)
    den = float(np.sum(weights * a_n * a_n))
    nt = max(0.0, float(np.sum(weights * a_n * ct) / max(den, 1e-300)))
    ng = max(0.0, float(np.sum(weights * a_n * cg) / max(den, 1e-300)))
    pred_t0 = nt * a_n
    pred_g0 = ng * a_n
    objective0 = normalized_sse(ct, pred_t0, weights) + normalized_sse(cg, pred_g0, weights)
    lags = np.arange(1, min(options.max_acf_lag, len(acf_centre_global) - 1) + 1)
    good = np.isfinite(acf_centre_global[lags])
    if np.any(good):
        acf0 = np.power(phi_n, lags)
        mse0 = float(np.mean((acf_centre_global[lags][good] - acf0[good]) ** 2))
        objective0 += options.acf_weight_physical * mse0

    n_obs = 2 * len(ms) + len(lags)
    obj1 = float(centre_fit["objective"])
    scalar = ScalarFit(
        phi_noise=phi_n,
        phi_physical=float(centre_fit["phi_physical"]),
        tau_noise_exponential_star=tau_exponential_from_phi(phi_n, centre.dt_star),
        tau_physical_exponential_star=tau_exponential_from_phi(float(centre_fit["phi_physical"]), centre.dt_star),
        tau_noise_integral_star=tau_integral_from_phi(phi_n, centre.dt_star),
        tau_physical_integral_star=tau_integral_from_phi(float(centre_fit["phi_physical"]), centre.dt_star),
        trace_physical=float(centre_fit["trace_physical"]),
        trace_noise=float(centre_fit["trace_noise"]),
        global_physical=float(centre_fit["global_physical"]),
        global_noise=float(centre_fit["global_noise"]),
        objective_noise_only=float(objective0),
        objective_two_component=obj1,
        aicc_noise_only=aicc(objective0, n_obs, 2),
        aicc_two_component=aicc(obj1, n_obs, 5),
        delta_aicc=aicc(objective0, n_obs, 2) - aicc(obj1, n_obs, 5),
        width_fit_r2_trace=float(width_fit["r2_trace"]),
        width_fit_r2_global=float(width_fit["r2_global"]),
        centre_fit_r2_trace=float(centre_fit["r2_trace"]),
        centre_fit_r2_global=float(centre_fit["r2_global"]),
        acf_fit_rmse_noise=float(width_fit["acf_rmse"]),
        acf_fit_rmse_centre=float(centre_fit["acf_rmse"]),
        design_condition_number=float(centre_fit["condition_number"]),
    )
    diagnostics = {
        "width_fit": width_fit,
        "centre_fit": centre_fit,
        "centre_noise_only_prediction_trace": pred_t0,
        "centre_noise_only_prediction_global": pred_g0,
        "centre_trace_observed": ct,
        "centre_global_observed": cg,
        "width_trace_observed": wt,
        "width_global_observed": wg,
        "acf_width_global": acf_width_global,
        "acf_width_rays": acf_width_rays,
        "acf_centre_global": acf_centre_global,
    }
    return scalar, diagnostics


# ---------------------------------------------------------------------------
# Full covariance inference with PSD constraints
# ---------------------------------------------------------------------------

def raw_covariance_decomposition(
    covariances: Sequence[np.ndarray],
    group_sizes: Sequence[int],
    n_groups: np.ndarray,
    phi_p: float,
    phi_n: float,
) -> Tuple[np.ndarray, np.ndarray]:
    ap = attenuation_ar1(np.asarray(group_sizes), phi_p)
    an = attenuation_ar1(np.asarray(group_sizes), phi_n)
    A = np.column_stack([ap, an])
    weights = np.maximum(n_groups - 1.0, 1.0)
    lhs = A.T @ (weights[:, None] * A)
    inv = np.linalg.pinv(lhs)
    C = np.stack(covariances, axis=0)
    rhs_p = np.tensordot(weights * A[:, 0], C, axes=(0, 0))
    rhs_n = np.tensordot(weights * A[:, 1], C, axes=(0, 0))
    coeff = inv @ np.stack([rhs_p.ravel(), rhs_n.ravel()], axis=0)
    shape = C.shape[1:]
    Cp = coeff[0].reshape(shape)
    Cn = coeff[1].reshape(shape)
    return 0.5 * (Cp + Cp.T), 0.5 * (Cn + Cn.T)


def psd_projection(C: np.ndarray) -> Tuple[np.ndarray, Dict[str, float]]:
    Csym = 0.5 * (C + C.T)
    evals, evecs = np.linalg.eigh(Csym)
    positive = np.maximum(evals, 0.0)
    Cpsd = (evecs * positive) @ evecs.T
    negative_mass = float(np.sum(np.abs(evals[evals < 0])))
    positive_mass = float(np.sum(positive))
    negative_fraction = negative_mass / max(negative_mass + positive_mass, 1.0e-300)
    relative_correction = float(
        np.linalg.norm(Cpsd - Csym, ord="fro") / max(np.linalg.norm(Csym, ord="fro"), 1.0e-300)
    )
    return Cpsd, {
        "negative_mass": negative_mass,
        "negative_fraction": negative_fraction,
        "relative_correction": relative_correction,
    }


def projected_covariance_fit(
    covariances: Sequence[np.ndarray],
    group_sizes: Sequence[int],
    n_groups: np.ndarray,
    phi_p: float,
    phi_n: float,
    options: FitOptions,
) -> Tuple[np.ndarray, np.ndarray, int, float]:
    Cp_raw, Cn_raw = raw_covariance_decomposition(
        covariances, group_sizes, n_groups, phi_p, phi_n
    )
    Cp, _ = psd_projection(Cp_raw)
    Cn, _ = psd_projection(Cn_raw)
    ap = attenuation_ar1(np.asarray(group_sizes), phi_p)
    an = attenuation_ar1(np.asarray(group_sizes), phi_n)
    weights = np.maximum(n_groups - 1.0, 1.0)
    H = np.array(
        [
            [np.sum(weights * ap * ap), np.sum(weights * ap * an)],
            [np.sum(weights * ap * an), np.sum(weights * an * an)],
        ]
    )
    step = 0.95 / max(float(np.linalg.eigvalsh(H)[-1]), 1.0e-300)
    Cstack = np.stack(covariances, axis=0)
    previous = np.inf
    for iteration in range(1, options.psd_iterations + 1):
        residual = (
            ap[:, None, None] * Cp[None, :, :]
            + an[:, None, None] * Cn[None, :, :]
            - Cstack
        )
        grad_p = np.tensordot(weights * ap, residual, axes=(0, 0))
        grad_n = np.tensordot(weights * an, residual, axes=(0, 0))
        Cp_new, _ = psd_projection(Cp - step * grad_p)
        Cn_new, _ = psd_projection(Cn - step * grad_n)
        residual_new = (
            ap[:, None, None] * Cp_new[None, :, :]
            + an[:, None, None] * Cn_new[None, :, :]
            - Cstack
        )
        objective = float(
            np.sum(weights[:, None, None] * residual_new * residual_new)
        )
        if np.isfinite(previous):
            relative = abs(previous - objective) / max(previous, 1.0e-300)
            if relative < options.psd_tolerance:
                Cp, Cn = Cp_new, Cn_new
                break
        Cp, Cn = Cp_new, Cn_new
        previous = objective
    denom = float(np.sum(weights[:, None, None] * Cstack * Cstack))
    relative_residual = float(np.sqrt(previous / max(denom, 1.0e-300)))
    return Cp, Cn, iteration, relative_residual


def noise_only_covariance_fit(
    covariances: Sequence[np.ndarray],
    group_sizes: Sequence[int],
    n_groups: np.ndarray,
    phi_n: float,
) -> np.ndarray:
    an = attenuation_ar1(np.asarray(group_sizes), phi_n)
    weights = np.maximum(n_groups - 1.0, 1.0)
    denom = float(np.sum(weights * an * an))
    Cn = np.tensordot(weights * an, np.stack(covariances), axes=(0, 0)) / max(denom, 1e-300)
    return psd_projection(Cn)[0]


def leave_one_m_out_cv(
    covariances: Sequence[np.ndarray],
    group_sizes: Sequence[int],
    n_groups: np.ndarray,
    phi_p: float,
    phi_n: float,
) -> Tuple[float, float]:
    errors_two = []
    errors_noise = []
    ms = np.asarray(group_sizes)
    for held in range(len(ms)):
        train = [i for i in range(len(ms)) if i != held]
        Ctrain = [covariances[i] for i in train]
        mtrain = [group_sizes[i] for i in train]
        ntrain = n_groups[train]
        Cp_raw, Cn_raw = raw_covariance_decomposition(Ctrain, mtrain, ntrain, phi_p, phi_n)
        Cp = psd_projection(Cp_raw)[0]
        Cn = psd_projection(Cn_raw)[0]
        pred = attenuation_ar1([ms[held]], phi_p)[0] * Cp + attenuation_ar1([ms[held]], phi_n)[0] * Cn
        target = covariances[held]
        errors_two.append(np.linalg.norm(pred - target, "fro") / max(np.linalg.norm(target, "fro"), 1e-300))
        Cn0 = noise_only_covariance_fit(Ctrain, mtrain, ntrain, phi_n)
        pred0 = attenuation_ar1([ms[held]], phi_n)[0] * Cn0
        errors_noise.append(np.linalg.norm(pred0 - target, "fro") / max(np.linalg.norm(target, "fro"), 1e-300))
    return float(np.mean(errors_two)), float(np.mean(errors_noise))


def infer_covariance_fit(centre: ChannelData, scalar: ScalarFit, options: FitOptions) -> CovarianceFit:
    covariances, _, _, n_groups = covariance_series(centre)
    Cp_raw, Cn_raw = raw_covariance_decomposition(
        covariances, centre.group_sizes, n_groups,
        scalar.phi_physical, scalar.phi_noise,
    )
    Cp_raw_psd, pdiag = psd_projection(Cp_raw)
    Cn_raw_psd, ndiag = psd_projection(Cn_raw)
    Cp, Cn, iterations, residual = projected_covariance_fit(
        covariances, centre.group_sizes, n_groups,
        scalar.phi_physical, scalar.phi_noise, options,
    )
    cv_two, cv_noise = leave_one_m_out_cv(
        covariances, centre.group_sizes, n_groups,
        scalar.phi_physical, scalar.phi_noise,
    )
    return CovarianceFit(
        C_physical=Cp,
        C_noise=Cn,
        C_physical_raw=Cp_raw,
        C_noise_raw=Cn_raw,
        raw_negative_mass_physical=float(pdiag["negative_mass"]),
        raw_negative_mass_noise=float(ndiag["negative_mass"]),
        raw_negative_fraction_physical=float(pdiag["negative_fraction"]),
        raw_negative_fraction_noise=float(ndiag["negative_fraction"]),
        projected_relative_correction_physical=float(
            np.linalg.norm(Cp - Cp_raw_psd, "fro") / max(np.linalg.norm(Cp_raw_psd, "fro"), 1e-300)
        ),
        projected_relative_correction_noise=float(
            np.linalg.norm(Cn - Cn_raw_psd, "fro") / max(np.linalg.norm(Cn_raw_psd, "fro"), 1e-300)
        ),
        weighted_relative_residual=residual,
        iterations=iterations,
        loocv_error_two_component=cv_two,
        loocv_error_noise_only=cv_noise,
    )


# ---------------------------------------------------------------------------
# Metrics, stationarity and far-angle tests
# ---------------------------------------------------------------------------

def covariance_metrics(theta: np.ndarray, Cp: np.ndarray, Cn: np.ndarray, far_angle_deg: float) -> Dict[str, float | np.ndarray]:
    n = len(theta)
    trace_p = float(np.trace(Cp))
    trace_n = float(np.trace(Cn))
    one = np.ones(n) / n
    global_p = float(one @ Cp @ one)
    global_n = float(one @ Cn @ one)
    evals, evecs = np.linalg.eigh(Cp)
    order = np.argsort(evals)[::-1]
    evals = np.maximum(evals[order], 0.0)
    evecs = evecs[:, order]
    if np.sum(evals) > 0:
        mode = evecs[:, 0] / np.linalg.norm(evecs[:, 0])
        e1 = float(evals[0] / np.sum(evals))
        uniform = np.ones(n) / np.sqrt(n)
        uniform_corr = abs(float(np.dot(mode, uniform)))
        participation = float(1.0 / np.sum(mode**4))
        dtheta = float(np.median(np.diff(theta))) if n > 1 else 10.0
        sector_n = max(1, min(n, int(round(10.0 / max(dtheta, 1.0e-12)))))
        energy = mode * mode
        max_sector = max(
            float(np.sum(energy[i : i + sector_n]))
            for i in range(n - sector_n + 1)
        )
        roughness = float(np.sum(np.diff(mode) ** 2))
    else:
        mode = np.full(n, np.nan)
        e1 = uniform_corr = participation = max_sector = roughness = np.nan

    diag = np.sqrt(np.maximum(np.diag(Cp), 0.0))
    corr = Cp / np.maximum(diag[:, None] * diag[None, :], 1.0e-300)
    cov_far = []
    corr_far = []
    for i in range(n):
        for j in range(i + 1, n):
            if abs(theta[j] - theta[i]) >= far_angle_deg:
                cov_far.append(Cp[i, j])
                corr_far.append(corr[i, j])
    cov_far_mean = float(np.mean(cov_far)) if cov_far else np.nan
    corr_far_mean = float(np.mean(corr_far)) if corr_far else np.nan

    return {
        "trace_physical": trace_p,
        "trace_noise": trace_n,
        "physical_trace_fraction_m1": trace_p / (trace_p + trace_n) if trace_p + trace_n > 0 else np.nan,
        "pointwise_physical_std_R": float(np.sqrt(max(trace_p / n, 0.0))),
        "global_physical_variance_R2": global_p,
        "global_noise_variance_R2": global_n,
        "global_physical_std_R": float(np.sqrt(max(global_p, 0.0))),
        "physical_global_fraction_m1": global_p / (global_p + global_n) if global_p + global_n > 0 else np.nan,
        "physical_angular_E1": e1,
        "uniform_mode_correlation": uniform_corr,
        "mode_participation_rays": participation,
        "max_10deg_mode_energy_fraction": max_sector,
        "mode_roughness": roughness,
        "far_angle_mean_covariance_R2": cov_far_mean,
        "far_angle_mean_correlation": corr_far_mean,
        "mode1": mode,
    }


def stationarity_metrics(X: np.ndarray, dt_star: float, prefix: str) -> Dict[str, float]:
    series = np.mean(X, axis=1)
    t = np.arange(len(series)) * dt_star
    slope = linregress(t, series)
    quartiles = np.array_split(series, 4)
    qmeans = np.array([np.mean(q) for q in quartiles])
    qvars = np.array([np.var(q, ddof=1) for q in quartiles])
    lev = levene(*quartiles, center="median")
    std = float(np.std(series, ddof=1))
    return {
        f"{prefix}_linear_slope_per_tstar": float(slope.slope),
        f"{prefix}_linear_trend_pvalue": float(slope.pvalue),
        f"{prefix}_max_quartile_mean_shift_in_std": float(np.max(np.abs(qmeans - np.mean(series))) / max(std, 1e-300)),
        f"{prefix}_quartile_variance_ratio": float(np.max(qvars) / max(np.min(qvars), 1e-300)),
        f"{prefix}_levene_pvalue": float(lev.pvalue),
    }


# ---------------------------------------------------------------------------
# Aligned moving-block bootstrap
# ---------------------------------------------------------------------------

def aligned_superblock_bootstrap(
    centre: ChannelData,
    width: ChannelData,
    rng: np.random.Generator,
) -> Tuple[ChannelData, ChannelData]:
    max_m = int(np.lcm.reduce(np.asarray(centre.group_sizes, dtype=int)))
    available_raw = min(m * len(centre.arrays[m]) for m in centre.group_sizes)
    n_super = available_raw // max_m
    if n_super < 4:
        raise ValueError("Too few aligned superblocks for bootstrap.")
    chosen = rng.integers(0, n_super, size=n_super)

    def resample_channel(channel: ChannelData) -> ChannelData:
        arrays: Dict[int, np.ndarray] = {}
        for m in channel.group_sizes:
            groups_per_super = max_m // m
            blocks = []
            X = channel.arrays[m]
            for b in chosen:
                start = b * groups_per_super
                stop = start + groups_per_super
                blocks.append(X[start:stop])
            arrays[m] = np.concatenate(blocks, axis=0)
        return ChannelData(channel.theta_deg.copy(), channel.group_sizes.copy(), arrays, channel.dt_star)

    return resample_channel(centre), resample_channel(width)


def bootstrap_case(
    centre: ChannelData,
    width: ChannelData,
    reference_mode: np.ndarray,
    options: FitOptions,
) -> pd.DataFrame:
    if options.bootstrap_replicates <= 0:
        return pd.DataFrame()
    rng = np.random.default_rng(options.random_seed)
    rows = []
    boot_options = FitOptions(**{**options.__dict__, "psd_iterations": 0})
    for b in range(options.bootstrap_replicates):
        cb, wb = aligned_superblock_bootstrap(centre, width, rng)
        scalar, _ = infer_scalar_model(cb, wb, boot_options)
        covs, _, _, ng = covariance_series(cb)
        Cp_raw, Cn_raw = raw_covariance_decomposition(
            covs, cb.group_sizes, ng, scalar.phi_physical, scalar.phi_noise
        )
        Cp = psd_projection(Cp_raw)[0]
        Cn = psd_projection(Cn_raw)[0]
        metrics = covariance_metrics(cb.theta_deg, Cp, Cn, options.far_angle_deg)
        mode = metrics.pop("mode1")
        alignment = (
            abs(float(np.dot(mode, reference_mode)))
            if np.all(np.isfinite(mode)) and np.all(np.isfinite(reference_mode))
            else np.nan
        )
        rows.append(
            {
                "replicate": b + 1,
                "phi_noise": scalar.phi_noise,
                "phi_physical": scalar.phi_physical,
                "tau_noise_exponential_star": scalar.tau_noise_exponential_star,
                "tau_physical_exponential_star": scalar.tau_physical_exponential_star,
                "tau_noise_integral_star": scalar.tau_noise_integral_star,
                "tau_physical_integral_star": scalar.tau_physical_integral_star,
                "delta_aicc": scalar.delta_aicc,
                "mode_alignment_with_reference": alignment,
                **{k: v for k, v in metrics.items() if np.isscalar(v)},
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Matched synthetic controls
# ---------------------------------------------------------------------------

def matrix_square_root(C: np.ndarray) -> np.ndarray:
    evals, evecs = np.linalg.eigh(0.5 * (C + C.T))
    evals = np.maximum(evals, 0.0)
    return evecs * np.sqrt(evals)


def simulate_ar1(n: int, phi: float, covariance_stationary: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    root = matrix_square_root(covariance_stationary)
    dim = covariance_stationary.shape[0]
    X = np.zeros((n, dim), dtype=float)
    X[0] = rng.standard_normal(dim) @ root.T
    innovation_scale = math.sqrt(max(1.0 - phi * phi, 0.0))
    for t in range(1, n):
        X[t] = phi * X[t - 1] + innovation_scale * (rng.standard_normal(dim) @ root.T)
    return X


def construct_group_arrays(X: np.ndarray, group_sizes: Sequence[int]) -> Dict[int, np.ndarray]:
    arrays = {}
    for m in group_sizes:
        ng = len(X) // m
        arrays[m] = X[: ng * m].reshape(ng, m, X.shape[1]).mean(axis=1)
    return arrays


def synthetic_controls(
    centre: ChannelData,
    scalar: ScalarFit,
    covfit: CovarianceFit,
    reference_metrics: Mapping[str, object],
    options: FitOptions,
) -> pd.DataFrame:
    if options.control_replicates <= 0:
        return pd.DataFrame()
    rng = np.random.default_rng(options.random_seed + 991)
    n = len(centre.arrays[1])
    rows = []
    reference_mode = np.asarray(reference_metrics["mode1"])
    for scenario in ("noise_only", "positive"):
        for rep in range(options.control_replicates):
            noise = simulate_ar1(n, scalar.phi_noise, covfit.C_noise, rng)
            physical = (
                simulate_ar1(n, scalar.phi_physical, covfit.C_physical, rng)
                if scenario == "positive"
                else np.zeros_like(noise)
            )
            centre_arrays = construct_group_arrays(noise + physical, centre.group_sizes)
            # The width calibrator is a matched noise-only channel.
            width_arrays = construct_group_arrays(
                simulate_ar1(n, scalar.phi_noise, covfit.C_noise, rng),
                centre.group_sizes,
            )
            cs = ChannelData(centre.theta_deg, centre.group_sizes, centre_arrays, centre.dt_star)
            ws = ChannelData(centre.theta_deg, centre.group_sizes, width_arrays, centre.dt_star)
            scalar_s, _ = infer_scalar_model(cs, ws, options)
            covs, _, _, ng = covariance_series(cs)
            Cp_raw, Cn_raw = raw_covariance_decomposition(
                covs, cs.group_sizes, ng, scalar_s.phi_physical, scalar_s.phi_noise
            )
            Cp = psd_projection(Cp_raw)[0]
            Cn = psd_projection(Cn_raw)[0]
            metrics = covariance_metrics(cs.theta_deg, Cp, Cn, options.far_angle_deg)
            mode = metrics.pop("mode1")
            rows.append(
                {
                    "scenario": scenario,
                    "replicate": rep + 1,
                    "phi_noise_recovered": scalar_s.phi_noise,
                    "phi_physical_recovered": scalar_s.phi_physical,
                    "delta_aicc": scalar_s.delta_aicc,
                    "mode_alignment_with_reference": (
                        abs(float(np.dot(mode, reference_mode)))
                        if np.all(np.isfinite(mode)) and np.all(np.isfinite(reference_mode))
                        else np.nan
                    ),
                    **{k: v for k, v in metrics.items() if np.isscalar(v)},
                }
            )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def quantile_summary(df: pd.DataFrame, columns: Iterable[str], prefix: str = "") -> Dict[str, float]:
    out: Dict[str, float] = {}
    for col in columns:
        if col not in df:
            continue
        x = df[col].to_numpy(float)
        if not np.any(np.isfinite(x)):
            out[f"{prefix}{col}_q025"] = np.nan
            out[f"{prefix}{col}_median"] = np.nan
            out[f"{prefix}{col}_q975"] = np.nan
            continue
        out[f"{prefix}{col}_q025"] = float(np.nanquantile(x, 0.025))
        out[f"{prefix}{col}_median"] = float(np.nanmedian(x))
        out[f"{prefix}{col}_q975"] = float(np.nanquantile(x, 0.975))
    return out


def save_case_plots(
    out: Path,
    case: str,
    centre: ChannelData,
    width: ChannelData,
    scalar: ScalarFit,
    diagnostics: Mapping[str, object],
    metrics: Mapping[str, object],
    bootstrap: pd.DataFrame,
    controls: pd.DataFrame,
) -> None:
    ms = np.asarray(centre.group_sizes)
    invm = 1.0 / ms
    cf = diagnostics["centre_fit"]
    wf = diagnostics["width_fit"]

    fig, axes = plt.subplots(2, 2, figsize=(11.5, 8), constrained_layout=True)
    axes[0, 0].scatter(invm, diagnostics["centre_trace_observed"], label="observed")
    axes[0, 0].plot(invm, cf["prediction_trace"], label="AR(1) physical + noise")
    axes[0, 0].plot(invm, diagnostics["centre_noise_only_prediction_trace"], ls="--", label="noise only")
    axes[0, 0].set_title("Centre pointwise variance")
    axes[0, 1].scatter(invm, diagnostics["centre_global_observed"], label="observed")
    axes[0, 1].plot(invm, cf["prediction_global"], label="AR(1) physical + noise")
    axes[0, 1].plot(invm, diagnostics["centre_noise_only_prediction_global"], ls="--", label="noise only")
    axes[0, 1].set_title("Centre global-mean variance")
    axes[1, 0].scatter(invm, diagnostics["width_trace_observed"], label="observed")
    axes[1, 0].plot(invm, wf["prediction_trace"], label="correlated noise fit")
    axes[1, 0].set_title("Width pointwise variance (noise calibrator)")
    axes[1, 1].scatter(invm, diagnostics["width_global_observed"], label="observed")
    axes[1, 1].plot(invm, wf["prediction_global"], label="correlated noise fit")
    axes[1, 1].set_title("Width global variance (noise calibrator)")
    for ax in axes.ravel():
        ax.set_xlabel("1 / temporal group size")
        ax.set_ylabel("variance")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8)
    fig.suptitle(
        f"{case}: correlated-noise variance model; "
        f"phi_n={scalar.phi_noise:.3f}, phi_p={scalar.phi_physical:.3f}"
    )
    fig.savefig(out / f"{case}_variance_model.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    ac_c = diagnostics["acf_centre_global"]
    ac_w = diagnostics["acf_width_global"]
    lag = np.arange(len(ac_c))
    pg = scalar.global_physical
    ng = scalar.global_noise
    pred_c = (
        (pg * scalar.phi_physical**lag + ng * scalar.phi_noise**lag) / (pg + ng)
        if pg + ng > 0
        else np.zeros_like(lag, dtype=float)
    )
    fig, ax = plt.subplots(figsize=(7.2, 4.5))
    ax.plot(lag * centre.dt_star, ac_c, marker="o", label="centre observed")
    ax.plot(lag * centre.dt_star, pred_c, label="centre fitted mixture")
    ax.plot(lag * centre.dt_star, ac_w, marker="s", label="width observed")
    ax.plot(lag * centre.dt_star, scalar.phi_noise**lag, label="width/noise AR(1)")
    ax.axhline(0, color="0.5", lw=0.8)
    ax.set_xlabel(r"lag $\tau^*$")
    ax.set_ylabel("autocorrelation")
    ax.set_title(f"{case}: ACF model consistency")
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / f"{case}_acf_model.png", dpi=300)
    plt.close(fig)

    mode = np.asarray(metrics["mode1"])
    fig, ax = plt.subplots(figsize=(7.2, 4.4))
    ax.plot(centre.theta_deg, mode, lw=2, label="inferred physical mode 1")
    ax.axhline(0, color="0.5", lw=0.8)
    ax.set_xlabel(r"$\theta$ [deg]")
    ax.set_ylabel("normalized mode amplitude")
    ax.set_title(
        f"{case}: physical angular mode; uniform correlation="
        f"{metrics['uniform_mode_correlation']:.3f}"
    )
    ax.grid(True, alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / f"{case}_physical_mode1.png", dpi=300)
    plt.close(fig)

    if not bootstrap.empty:
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), constrained_layout=True)
        axes[0].hist(bootstrap["physical_trace_fraction_m1"], bins=25, alpha=0.8)
        axes[0].axvline(metrics["physical_trace_fraction_m1"], color="black", lw=2)
        axes[0].set_xlabel("physical trace fraction at m=1")
        axes[0].set_title("Aligned moving-block bootstrap")
        axes[1].hist(bootstrap["uniform_mode_correlation"], bins=25, alpha=0.8)
        axes[1].axvline(metrics["uniform_mode_correlation"], color="black", lw=2)
        axes[1].set_xlabel("uniform breathing correlation")
        axes[1].set_title("Mode-shape uncertainty")
        fig.suptitle(case)
        fig.savefig(out / f"{case}_bootstrap.png", dpi=300, bbox_inches="tight")
        plt.close(fig)

    if not controls.empty:
        fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), constrained_layout=True)
        for scenario, g in controls.groupby("scenario"):
            axes[0].hist(g["physical_trace_fraction_m1"], bins=20, alpha=0.55, label=scenario)
            axes[1].hist(g["mode_alignment_with_reference"], bins=20, alpha=0.55, label=scenario)
        axes[0].set_xlabel("recovered physical trace fraction")
        axes[1].set_xlabel("recovered mode alignment")
        for ax in axes:
            ax.legend()
            ax.grid(True, alpha=0.2)
        fig.suptitle(f"{case}: matched synthetic controls")
        fig.savefig(out / f"{case}_synthetic_controls.png", dpi=300, bbox_inches="tight")
        plt.close(fig)


# ---------------------------------------------------------------------------
# Case analysis
# ---------------------------------------------------------------------------

def analyze_case(
    case_dir: Path,
    out_dir: Path,
    angular_smoothing: int,
    options: FitOptions,
) -> Tuple[Dict[str, float], pd.DataFrame, pd.DataFrame]:
    centre, width = load_case_channels(case_dir, angular_smoothing)
    scalar, diagnostics = infer_scalar_model(centre, width, options)
    covfit = infer_covariance_fit(centre, scalar, options)
    metrics = covariance_metrics(
        centre.theta_deg,
        covfit.C_physical,
        covfit.C_noise,
        options.far_angle_deg,
    )
    mode = np.asarray(metrics["mode1"])
    bootstrap = bootstrap_case(centre, width, mode, options)
    controls = synthetic_controls(centre, scalar, covfit, metrics, options)

    centre_stationarity = stationarity_metrics(centre.arrays[1], centre.dt_star, "centre")
    width_stationarity = stationarity_metrics(width.arrays[1], width.dt_star, "width")

    physical_model_supported = bool(
        scalar.delta_aicc > 10.0
        and covfit.loocv_error_two_component < covfit.loocv_error_noise_only
        and scalar.design_condition_number < 50.0
    )
    controls = controls.copy()
    if not controls.empty:
        controls["two_component_detected"] = controls["delta_aicc"] > 10.0
        noise_controls = controls[controls["scenario"] == "noise_only"]
        positive_controls = controls[controls["scenario"] == "positive"]
        control_summary = {
            "negative_control_false_detection_rate": float(noise_controls["two_component_detected"].mean()),
            "positive_control_detection_rate": float(positive_controls["two_component_detected"].mean()),
            "positive_control_mode_alignment_median": float(positive_controls["mode_alignment_with_reference"].median()),
            "negative_control_delta_aicc_median": float(noise_controls["delta_aicc"].median()),
            "positive_control_delta_aicc_median": float(positive_controls["delta_aicc"].median()),
        }
    else:
        control_summary = {}

    scalar_dict = scalar.__dict__.copy()
    cov_dict = {
        key: value
        for key, value in covfit.__dict__.items()
        if np.isscalar(value)
    }
    summary = {
        "case": case_dir.name,
        "Kn": case_name_to_kn(case_dir.name),
        "angular_smoothing_rays": angular_smoothing,
        "n_rays": len(centre.theta_deg),
        "n_raw_snapshots": len(centre.arrays[1]),
        "dt_star": centre.dt_star,
        "physical_model_supported": physical_model_supported,
        **scalar_dict,
        **cov_dict,
        **{k: v for k, v in metrics.items() if np.isscalar(v)},
        **centre_stationarity,
        **width_stationarity,
        **control_summary,
        **quantile_summary(
            bootstrap,
            [
                "phi_noise",
                "phi_physical",
                "tau_noise_exponential_star",
                "tau_physical_exponential_star",
                "tau_noise_integral_star",
                "tau_physical_integral_star",
                "delta_aicc",
                "physical_trace_fraction_m1",
                "physical_global_fraction_m1",
                "physical_angular_E1",
                "uniform_mode_correlation",
                "far_angle_mean_covariance_R2",
                "far_angle_mean_correlation",
                "mode_alignment_with_reference",
                "global_physical_std_R",
            ],
            prefix="bootstrap_",
        ),
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({"theta_deg": centre.theta_deg, "physical_mode1": mode}).to_csv(
        out_dir / "physical_mode1.csv", index=False
    )
    np.savez_compressed(
        out_dir / "inferred_covariances.npz",
        theta_deg=centre.theta_deg,
        C_physical=covfit.C_physical,
        C_noise=covfit.C_noise,
        C_physical_raw=covfit.C_physical_raw,
        C_noise_raw=covfit.C_noise_raw,
        physical_mode1=mode,
    )
    bootstrap.to_csv(out_dir / "moving_block_bootstrap.csv", index=False)
    controls.to_csv(out_dir / "synthetic_controls.csv", index=False)
    pd.DataFrame(diagnostics["width_fit"]["profile"]).drop(
        columns=["prediction_trace", "prediction_global"], errors="ignore"
    ).to_csv(out_dir / "noise_phi_profile.csv", index=False)
    pd.DataFrame(diagnostics["centre_fit"]["profile"]).drop(
        columns=["prediction_trace", "prediction_global", "prediction_acf"], errors="ignore"
    ).to_csv(out_dir / "physical_phi_profile.csv", index=False)
    save_case_plots(out_dir, case_dir.name, centre, width, scalar, diagnostics, metrics, bootstrap, controls)
    return summary, bootstrap, controls


# ---------------------------------------------------------------------------
# Synthetic self-test
# ---------------------------------------------------------------------------

def simulate_test_channel(
    n: int,
    theta: np.ndarray,
    group_sizes: Sequence[int],
    phi_p: float,
    phi_n: float,
    physical_scale: float,
    noise_scale: float,
    rng: np.random.Generator,
) -> Tuple[ChannelData, ChannelData]:
    dim = len(theta)
    uniform = np.ones(dim) / np.sqrt(dim)
    Cp = physical_scale * np.outer(uniform, uniform) + 0.02 * physical_scale * np.eye(dim) / dim
    Cn = noise_scale * np.eye(dim)
    physical = simulate_ar1(n, phi_p, Cp, rng)
    noise_c = simulate_ar1(n, phi_n, Cn, rng)
    noise_w = simulate_ar1(n, phi_n, Cn, rng)
    centre = ChannelData(theta, list(group_sizes), construct_group_arrays(physical + noise_c, group_sizes), 0.3)
    width = ChannelData(theta, list(group_sizes), construct_group_arrays(noise_w, group_sizes), 0.3)
    return centre, width


def self_test() -> None:
    rng = np.random.default_rng(44)
    theta = np.linspace(120, 179, 30)
    group_sizes = [1, 2, 4, 8, 16]
    centre, width = simulate_test_channel(
        512, theta, group_sizes,
        phi_p=0.70, phi_n=0.25,
        physical_scale=8.0e-5,
        noise_scale=2.0e-5,
        rng=rng,
    )
    options = FitOptions(
        phi_grid_size=240,
        psd_iterations=100,
        bootstrap_replicates=8,
        control_replicates=3,
        random_seed=22,
    )
    scalar, _ = infer_scalar_model(centre, width, options)
    covfit = infer_covariance_fit(centre, scalar, options)
    metrics = covariance_metrics(theta, covfit.C_physical, covfit.C_noise, 15.0)
    if not (abs(scalar.phi_noise - 0.25) < 0.25):
        raise AssertionError(f"Noise phi recovery failed: {scalar.phi_noise}")
    if not (abs(scalar.phi_physical - 0.70) < 0.30):
        raise AssertionError(f"Physical phi recovery failed: {scalar.phi_physical}")
    if not (metrics["uniform_mode_correlation"] > 0.70):
        raise AssertionError("Uniform physical mode was not recovered.")
    print("SELF-TEST PASS")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", help="Root containing arbitrary Kn* temporal-coarse-graining folders")
    ap.add_argument("--out", default="correlated_noise_inference")
    ap.add_argument("--angular-smoothing", nargs="+", type=int, default=[1, 3, 5])
    ap.add_argument("--bootstrap", type=int, default=200)
    ap.add_argument("--controls", type=int, default=40)
    ap.add_argument("--phi-grid", type=int, default=500)
    ap.add_argument("--max-acf-lag", type=int, default=8)
    ap.add_argument("--far-angle-deg", type=float, default=15.0)
    ap.add_argument("--seed", type=int, default=12031)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()

    if args.self_test:
        self_test()
        return
    if not args.root:
        ap.error("--root is required unless --self-test is used.")

    root = Path(args.root)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    options = FitOptions(
        max_acf_lag=args.max_acf_lag,
        phi_grid_size=args.phi_grid,
        far_angle_deg=args.far_angle_deg,
        bootstrap_replicates=args.bootstrap,
        control_replicates=args.controls,
        random_seed=args.seed,
    )

    summaries = []
    for case_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        for angular_smoothing in args.angular_smoothing:
            case_out = out / case_dir.name / f"ang{angular_smoothing}"
            print(f"ANALYZE {case_dir.name}, angular smoothing={angular_smoothing}")
            try:
                case_options = options
                if angular_smoothing != 1:
                    case_options = FitOptions(
                        **{
                            **options.__dict__,
                            "bootstrap_replicates": 0,
                            "control_replicates": 0,
                        }
                    )
                summary, _, _ = analyze_case(
                    case_dir, case_out, angular_smoothing, case_options
                )
                summaries.append(summary)
            except Exception as exc:
                print(f"FAILED {case_dir.name} ang={angular_smoothing}: {exc}")
                raise

    df = pd.DataFrame(summaries)
    df.to_csv(out / "correlated_noise_inference_summary.csv", index=False)
    if df.empty:
        raise SystemExit("No case was analyzed.")

    # Primary summary uses no angular smoothing.
    primary = df[df["angular_smoothing_rays"] == 1].copy()
    primary = primary.sort_values("Kn")
    fig, axes = plt.subplots(2, 2, figsize=(12, 8), constrained_layout=True)
    axes[0, 0].semilogx(primary["Kn"], 100 * primary["physical_trace_fraction_m1"], marker="o")
    axes[0, 0].fill_between(
        primary["Kn"],
        100 * primary["bootstrap_physical_trace_fraction_m1_q025"],
        100 * primary["bootstrap_physical_trace_fraction_m1_q975"],
        alpha=0.25,
    )
    axes[0, 0].set_ylabel("physical trace fraction [%]")
    axes[0, 1].semilogx(primary["Kn"], 100 * primary["physical_global_fraction_m1"], marker="o")
    axes[0, 1].fill_between(
        primary["Kn"],
        100 * primary["bootstrap_physical_global_fraction_m1_q025"],
        100 * primary["bootstrap_physical_global_fraction_m1_q975"],
        alpha=0.25,
    )
    axes[0, 1].set_ylabel("physical global fraction [%]")
    axes[1, 0].semilogx(primary["Kn"], primary["uniform_mode_correlation"], marker="o")
    axes[1, 0].fill_between(
        primary["Kn"],
        primary["bootstrap_uniform_mode_correlation_q025"],
        primary["bootstrap_uniform_mode_correlation_q975"],
        alpha=0.25,
    )
    axes[1, 0].set_ylabel("uniform breathing correlation")
    axes[1, 1].semilogx(primary["Kn"], primary["global_physical_std_R"], marker="o")
    axes[1, 1].fill_between(
        primary["Kn"],
        primary["bootstrap_global_physical_std_R_q025"],
        primary["bootstrap_global_physical_std_R_q975"],
        alpha=0.25,
    )
    axes[1, 1].set_ylabel(r"absolute physical global std, $\sigma_{s/R}$")
    for ax in axes.ravel():
        ax.set_xlabel("Kn")
        ax.grid(True, alpha=0.25)
    fig.suptitle("Correlated-noise-corrected bow-layer displacement statistics")
    fig.savefig(out / "Fig_correlated_noise_summary.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    # Model-comparison and identifiability summary.
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.5), constrained_layout=True)
    axes[0].semilogx(primary["Kn"], primary["delta_aicc"], marker="o")
    axes[0].axhline(0, color="black", lw=0.8)
    axes[0].set_ylabel(r"$\Delta AIC_c$ (noise only minus two component)")
    axes[1].semilogx(primary["Kn"], primary["loocv_error_noise_only"], marker="s", label="noise only")
    axes[1].semilogx(primary["Kn"], primary["loocv_error_two_component"], marker="o", label="physical + noise")
    axes[1].set_ylabel("leave-one-m-out covariance error")
    axes[1].legend()
    for ax in axes:
        ax.set_xlabel("Kn")
        ax.grid(True, alpha=0.25)
    fig.suptitle("Does the physical component improve out-of-sample prediction?")
    fig.savefig(out / "Fig_model_comparison.png", dpi=300, bbox_inches="tight")
    plt.close(fig)

    metadata = {
        "model": "C_m = A_m(phi_p) C_p + A_m(phi_n) C_n",
        "noise_calibrator": "10-90 width channel",
        "bootstrap": "aligned resampling of common 16-snapshot superblocks",
        "controls": "matched multivariate AR(1) noise-only and physical-plus-noise controls",
        "options": options.__dict__,
    }
    (out / "analysis_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
