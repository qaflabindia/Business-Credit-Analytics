"""
Macro and commodity scenario path generator.

Generates correlated AR(1) monthly paths for four scenarios:
  baseline | severe_demand | geopolitical_supply | disorderly_transition
"""
import numpy as np
import pandas as pd
from typing import List

from ..config import MACRO_BASELINE, SCENARIOS


# AR(1) volatility parameters (monthly standard deviation)
_AR_PARAMS = {
    "brent_usd_bbl":          {"rho": 0.85, "sigma": 7.0},
    "henry_hub_usd_mmbtu":    {"rho": 0.80, "sigma": 0.45},
    "ttf_usd_mmbtu":          {"rho": 0.80, "sigma": 1.20},
    "jkm_usd_mmbtu":          {"rho": 0.80, "sigma": 1.60},
    "global_gdp_yoy":         {"rho": 0.70, "sigma": 0.70},
    "us_gdp_yoy":             {"rho": 0.75, "sigma": 0.80},
    "eu_gdp_yoy":             {"rho": 0.70, "sigma": 0.65},
    "uk_gdp_yoy":             {"rho": 0.70, "sigma": 0.70},
    "unemployment_us":        {"rho": 0.92, "sigma": 0.25},
    "bbb_spread_bps":         {"rho": 0.88, "sigma": 18.0},
    "policy_rate_bps":        {"rho": 0.95, "sigma": 12.0},
    "carbon_price_usd_tco2":  {"rho": 0.90, "sigma": 4.0,  "trend_per_month": 0.40},
    "usd_index":              {"rho": 0.90, "sigma": 1.20},
    "shipping_cost_index":    {"rho": 0.80, "sigma": 8.0},
}

_VAR_NAMES = list(_AR_PARAMS.keys())
_N_VARS = len(_VAR_NAMES)

# Pairwise correlations between innovation terms
_CORR_PAIRS = [
    ("brent_usd_bbl",       "henry_hub_usd_mmbtu",  0.40),
    ("brent_usd_bbl",       "ttf_usd_mmbtu",        0.45),
    ("brent_usd_bbl",       "jkm_usd_mmbtu",        0.50),
    ("henry_hub_usd_mmbtu", "ttf_usd_mmbtu",        0.55),
    ("henry_hub_usd_mmbtu", "jkm_usd_mmbtu",        0.50),
    ("ttf_usd_mmbtu",       "jkm_usd_mmbtu",        0.70),
    ("brent_usd_bbl",       "global_gdp_yoy",       0.35),
    ("global_gdp_yoy",      "us_gdp_yoy",           0.80),
    ("global_gdp_yoy",      "eu_gdp_yoy",           0.70),
    ("global_gdp_yoy",      "uk_gdp_yoy",           0.65),
    ("us_gdp_yoy",          "unemployment_us",      -0.75),
    ("bbb_spread_bps",      "global_gdp_yoy",       -0.50),
    ("bbb_spread_bps",      "brent_usd_bbl",        -0.30),
    ("bbb_spread_bps",      "unemployment_us",       0.60),
    ("policy_rate_bps",     "us_gdp_yoy",            0.40),
    ("policy_rate_bps",     "unemployment_us",       -0.45),
    ("brent_usd_bbl",       "shipping_cost_index",   0.45),
    ("brent_usd_bbl",       "usd_index",            -0.35),
    ("carbon_price_usd_tco2","brent_usd_bbl",        0.20),
]


def _build_cholesky() -> np.ndarray:
    idx = {v: i for i, v in enumerate(_VAR_NAMES)}
    corr = np.eye(_N_VARS)
    for v1, v2, rho in _CORR_PAIRS:
        i, j = idx[v1], idx[v2]
        corr[i, j] = rho
        corr[j, i] = rho
    # Ensure positive-definiteness
    eigvals = np.linalg.eigvalsh(corr)
    if eigvals.min() < 1e-6:
        eps = abs(eigvals.min()) + 0.01
        corr = corr + np.eye(_N_VARS) * eps
        d = np.sqrt(np.diag(corr))
        corr = corr / np.outer(d, d)
    return np.linalg.cholesky(corr)


_CHOL = _build_cholesky()


def _ar1_path(n: int, mu: float, rho: float, sigma: float,
              trend: float, innovations: np.ndarray) -> np.ndarray:
    """Simulate one AR(1) path with optional deterministic trend."""
    x = np.empty(n)
    x[0] = mu + sigma * innovations[0]
    for t in range(1, n):
        mu_t = mu + trend * t
        x[t] = mu_t * (1 - rho) + rho * x[t - 1] + sigma * innovations[t]
    return x


def _apply_overlay(values: np.ndarray, scenario_id: str, n: int) -> np.ndarray:
    """Apply scenario-specific additive / multiplicative overlays."""
    idx = {v: i for i, v in enumerate(_VAR_NAMES)}
    v = values.copy()

    if scenario_id == "baseline":
        pass  # no overlay

    elif scenario_id == "severe_demand":
        s0, s1, s2 = min(30, n - 1), min(42, n - 1), min(60, n - 1)
        for t in range(s0, min(s2 + 1, n)):
            k = (t - s0) / max(s1 - s0, 1) if t <= s1 else 1.0 - 0.65 * (t - s1) / max(s2 - s1, 1)
            k = float(np.clip(k, 0.0, 1.0))
            v[t, idx["us_gdp_yoy"]]           -= 4.6 * k
            v[t, idx["global_gdp_yoy"]]       -= 3.5 * k
            v[t, idx["eu_gdp_yoy"]]           -= 3.0 * k
            v[t, idx["unemployment_us"]]       += 6.0 * k
            v[t, idx["brent_usd_bbl"]]        *= (1.0 - 0.35 * k)
            v[t, idx["bbb_spread_bps"]]        += 250.0 * k
            v[t, idx["policy_rate_bps"]]       -= 200.0 * k

    elif scenario_id == "geopolitical_supply":
        s0, s1, s2 = min(45, n - 1), min(54, n - 1), min(72, n - 1)
        for t in range(s0, min(s2 + 1, n)):
            k = (t - s0) / max(s1 - s0, 1) if t <= s1 else 1.0 - 0.80 * (t - s1) / max(s2 - s1, 1)
            k = float(np.clip(k, 0.0, 1.0))
            v[t, idx["brent_usd_bbl"]]           *= (1.0 + 0.50 * k)
            v[t, idx["ttf_usd_mmbtu"]]            *= (1.0 + 0.70 * k)
            v[t, idx["jkm_usd_mmbtu"]]            *= (1.0 + 0.60 * k)
            v[t, idx["henry_hub_usd_mmbtu"]]      *= (1.0 + 0.30 * k)
            v[t, idx["shipping_cost_index"]]       *= (1.0 + 0.80 * k)
            v[t, idx["global_gdp_yoy"]]            -= 1.5 * k
            v[t, idx["usd_index"]]                 += 5.0 * k
            v[t, idx["bbb_spread_bps"]]            += 80.0 * k

    elif scenario_id == "disorderly_transition":
        s0 = min(60, n - 1)
        for t in range(s0, n):
            k = float(min(1.0, (t - s0) / 36.0))
            v[t, idx["brent_usd_bbl"]]             *= (1.0 - 0.20 * k)
            v[t, idx["henry_hub_usd_mmbtu"]]        *= (1.0 - 0.10 * k)
            v[t, idx["carbon_price_usd_tco2"]]      *= (1.0 + 1.50 * k)
            v[t, idx["bbb_spread_bps"]]              += 50.0 * k

    return v


def _apply_floors(values: np.ndarray) -> np.ndarray:
    idx = {v: i for i, v in enumerate(_VAR_NAMES)}
    v = values.copy()
    v[:, idx["brent_usd_bbl"]]         = np.maximum(v[:, idx["brent_usd_bbl"]], 15.0)
    v[:, idx["henry_hub_usd_mmbtu"]]   = np.maximum(v[:, idx["henry_hub_usd_mmbtu"]], 1.50)
    v[:, idx["ttf_usd_mmbtu"]]         = np.maximum(v[:, idx["ttf_usd_mmbtu"]], 2.0)
    v[:, idx["jkm_usd_mmbtu"]]         = np.maximum(v[:, idx["jkm_usd_mmbtu"]], 2.0)
    v[:, idx["bbb_spread_bps"]]        = np.maximum(v[:, idx["bbb_spread_bps"]], 80.0)
    v[:, idx["carbon_price_usd_tco2"]] = np.maximum(v[:, idx["carbon_price_usd_tco2"]], 5.0)
    v[:, idx["unemployment_us"]]       = np.clip(v[:, idx["unemployment_us"]], 2.5, 15.0)
    v[:, idx["shipping_cost_index"]]   = np.maximum(v[:, idx["shipping_cost_index"]], 30.0)
    return v


def generate_macro_paths(
    n_months: int,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenarios: List[str] | None = None,
) -> pd.DataFrame:
    """Generate monthly macro/commodity paths for all requested scenarios."""
    if scenarios is None:
        scenarios = SCENARIOS

    raw = rng.standard_normal((n_months, _N_VARS))
    correlated = raw @ _CHOL.T   # shape (n_months, n_vars)

    results = []
    for scenario in scenarios:
        values = np.empty((n_months, _N_VARS))
        for j, var in enumerate(_VAR_NAMES):
            p = _AR_PARAMS[var]
            mu = MACRO_BASELINE[var]
            trend = p.get("trend_per_month", 0.0)
            values[:, j] = _ar1_path(n_months, mu, p["rho"], p["sigma"],
                                     trend, correlated[:, j])

        values = _apply_overlay(values, scenario, n_months)
        values = _apply_floors(values)

        df = pd.DataFrame(values, columns=_VAR_NAMES)
        df.insert(0, "as_of_month", months)
        df.insert(1, "scenario_id", scenario)
        results.append(df)

    return pd.concat(results, ignore_index=True)
