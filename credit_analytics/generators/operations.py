"""
Vectorized monthly operational data generator.

borrower_operations_m grain: (borrower_id, as_of_month)
Produces production volumes, realised prices, margins, lifting costs.
"""
import numpy as np
import pandas as pd


_SEGMENT_PROD_PARAMS = {
    "supermajor":           {"kboed_median": 3_000, "gas_share": 0.35},
    "large_integrated":     {"kboed_median":   700, "gas_share": 0.30},
    "independent_upstream": {"kboed_median":    80, "gas_share": 0.40},
    "midstream_lng":        {"kboed_median":    50, "gas_share": 0.80},
    "refining_marketing":   {"kboed_median":     0, "gas_share": 0.00},
    "oilfield_services":    {"kboed_median":     0, "gas_share": 0.00},
    "trading_petrochemicals":{"kboed_median":    0, "gas_share": 0.00},
}

_DECLINE_RATE_MONTHLY = 0.003
_CAPEX_BOOST_RATE     = 0.005


def simulate_operations_monthly(
    borrowers: pd.DataFrame,
    macro_m: pd.DataFrame,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return borrower_operations_m — fully vectorized over borrowers."""

    macro = macro_m[macro_m["scenario_id"] == scenario_id].set_index("as_of_month")

    N = len(borrowers)
    M = len(months)

    bid_arr     = borrowers["borrower_id"].values
    seg_arr     = borrowers["segment"].values
    has_res     = borrowers["has_reserves"].values.astype(bool)

    # Initial production (kboed) — lognormal within each segment
    init_prod = np.zeros(N)
    gas_share = np.zeros(N)
    for i, (seg, hr) in enumerate(zip(seg_arr, has_res)):
        pp = _SEGMENT_PROD_PARAMS[seg]
        med = pp["kboed_median"]
        if med > 0 and hr:
            init_prod[i] = np.exp(np.log(max(med, 1)) + 0.50 * rng.normal())
        gas_share[i] = pp["gas_share"]

    # Production noise, outages (all pre-allocated)
    eps_prod          = rng.normal(0, 0.03, (N, M))
    outage_days       = rng.poisson(lam=0.3, size=(N, M)).astype(float)
    planned_maint_days = np.zeros((N, M))
    for i in range(N):
        if not has_res[i]:
            continue
        n_maint = max(1, M // 6)
        maint_idx = rng.choice(M, size=n_maint, replace=False)
        planned_maint_days[i, maint_idx] = rng.uniform(3, 7, n_maint)

    # Simulate production path (N, M) — time loop is only M iterations (not N×M)
    prod_kboed = np.zeros((N, M))
    prod_kboed[:, 0] = np.maximum(init_prod * (1 + eps_prod[:, 0]), 0.0)
    decline_mult = 1 - _DECLINE_RATE_MONTHLY + _CAPEX_BOOST_RATE

    for t in range(1, M):
        outage_mult = 1 - outage_days[:, t] / 30.0 - planned_maint_days[:, t] / 30.0
        outage_mult = np.clip(outage_mult, 0.7, 1.0)
        prod_kboed[:, t] = np.maximum(
            prod_kboed[:, t - 1] * decline_mult * outage_mult * (1 + eps_prod[:, t]), 0.0
        )

    # Zero out production for non-upstream segments
    prod_kboed[~has_res, :] = 0.0

    # Macro arrays over time (M,)
    brent_arr  = np.array([macro.loc[m, "brent_usd_bbl"]       if m in macro.index else 75.0  for m in months])
    gas_arr    = np.array([macro.loc[m, "henry_hub_usd_mmbtu"] if m in macro.index else 3.5   for m in months])

    # Realised prices: (N, M)
    oil_diff  = rng.normal(-2.0, 2.5, (N, M))
    gas_diff  = rng.normal(-0.10, 0.20, (N, M))
    realised_oil = np.maximum(brent_arr[None, :] + oil_diff, 5.0)   # (N, M)
    realised_gas = np.maximum(gas_arr[None, :]  + gas_diff, 0.5)

    # Lifting costs: (N, M) — only for upstream
    base_lift = rng.uniform(8, 22, (N, M))
    base_lift[~has_res, :] = 0.0
    lift_cost = np.maximum(base_lift * (1 + 0.15 * rng.normal(0, 1, (N, M))), 0.0)

    # Crack spread and chem margin: (M,)
    crack_spread = np.maximum(brent_arr * 0.15 + rng.normal(0, 3, M), 0.0)
    chem_margin  = np.maximum(250 + rng.normal(0, 50, M), 50.0)

    # Scope 1+2 emissions: (N, M)
    scope12 = prod_kboed * 0.02

    # Segment masks for refining / trading
    refining_mask = (seg_arr == "refining_marketing")
    trading_mask  = (seg_arr == "trading_petrochemicals")

    # ── Assemble DataFrame from pre-computed arrays ────────────────────────────
    # Repeat along time axis: (N × M) long arrays
    borrower_ids_rep = np.repeat(bid_arr, M)
    months_rep       = np.tile(months, N)

    liq_prod    = (prod_kboed * (1 - gas_share[:, None])).ravel()
    gas_prod    = (prod_kboed * gas_share[:, None] * 0.18).ravel()
    total_prod  = prod_kboed.ravel()
    r_oil       = realised_oil.ravel()
    r_gas       = realised_gas.ravel()
    lift        = lift_cost.ravel()
    maint_d     = planned_maint_days.ravel()
    outage_d    = outage_days.ravel()
    scope       = scope12.ravel()

    # Crack spread / chem margin per borrower-month
    crack_rep  = np.tile(crack_spread, N)
    chem_rep   = np.tile(chem_margin,  N)

    has_res_rep   = np.repeat(has_res,   M)
    refining_rep  = np.repeat(refining_mask, M)
    trading_rep   = np.repeat(trading_mask,  M)

    df = pd.DataFrame({
        "borrower_id":                   borrower_ids_rep,
        "as_of_month":                   months_rep,
        "scenario_id":                   scenario_id,
        "liq_prod_kboed":                np.where(has_res_rep, liq_prod, 0.0),
        "gas_prod_mmscfd":               np.where(has_res_rep, gas_prod, 0.0),
        "total_prod_kboed":              np.where(has_res_rep, total_prod, 0.0),
        "realised_oil_price_usd_bbl":    np.where(has_res_rep, r_oil, float("nan")),
        "realised_gas_price_usd_mmbtu":  np.where(has_res_rep, r_gas, float("nan")),
        "refining_margin_usd_bbl":       np.where(refining_rep, crack_rep, float("nan")),
        "chemical_margin_usd_tonne":     np.where(trading_rep,  chem_rep,  float("nan")),
        "lifting_cost_usd_boe":          np.where(has_res_rep, lift, float("nan")),
        "planned_maintenance_days":      maint_d,
        "unplanned_outage_days":         outage_d,
        "spill_count":                   rng.poisson(0.01, N * M),
        "scope1_2_ktco2e":               np.where(has_res_rep, scope, 0.0),
    })

    return df
