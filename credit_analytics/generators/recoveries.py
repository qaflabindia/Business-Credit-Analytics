"""
Recovery cash flow simulator.

For each default event, simulate:
  - resolution time (6-36 months)
  - recovery rate driven by collateral, seniority, macro state
  - monthly recovery cash flows
  - final LGD

logit(RR) = γ0 + γ1*CollateralCoverage + γ2*Seniority + γ3*PDPshare
           + γ4*HedgeCoverage - γ5*DecommBurden - γ6*BBBspread
           - γ7*IndustryDefaultRate - γ8*ResolutionTime + ω
LGD = 1 - RR
"""
import numpy as np
import pandas as pd
from scipy.special import expit


_SENIORITY_RR_BASE = {
    "senior_secured":   0.70,
    "senior_unsecured": 0.48,
    "subordinated":     0.25,
}

# Recovery model coefficients (logit scale)
_GAMMA = {
    "intercept":              0.50,
    "collateral_coverage":    0.60,
    "seniority_secured":      0.80,
    "pdp_share":              0.40,
    "hedge_coverage":         0.30,
    "decomm_burden":         -0.50,
    "bbb_spread_z":          -0.45,
    "industry_default_rate": -0.35,
    "resolution_time_z":     -0.25,
}


def simulate_recoveries(
    defaults: pd.DataFrame,
    facilities: pd.DataFrame,
    borrowers: pd.DataFrame,
    snapshots: pd.DataFrame,
    reserves_q: pd.DataFrame,
    macro_m: pd.DataFrame,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return recovery_cashflow_fact."""
    if len(defaults) == 0:
        return pd.DataFrame()

    macro = macro_m[macro_m["scenario_id"] == scenario_id].set_index("as_of_month")
    fac_map = facilities.set_index("facility_id")
    brw_map = borrowers.set_index("borrower_id")
    snap_sub = snapshots[snapshots["scenario_id"] == scenario_id]

    # Industry default rate proxy (rolling 12m) — computed later
    # For now use a scalar approximation
    total_borrowers = len(borrowers)

    rows = []

    for _, def_row in defaults.iterrows():
        fid = def_row["facility_id"]
        bid = def_row["borrower_id"]
        def_date = pd.Timestamp(def_row["default_date"])
        ead = float(def_row["default_ead_usd_m"])

        if fid not in fac_map.index or bid not in brw_map.index:
            continue

        fac = fac_map.loc[fid]
        brw = brw_map.loc[bid]

        seniority = str(fac["seniority"])

        # Resolution time (months): 6-36
        base_res = 18 if seniority == "senior_secured" else (24 if seniority == "senior_unsecured" else 32)
        resolution_months = int(np.clip(rng.normal(base_res, 6), 6, 48))

        # Collateral coverage at default
        snap_def = snap_sub[
            (snap_sub["facility_id"] == fid) & (snap_sub["as_of_month"] == def_date)
        ]
        coll_cov = float(snap_def["collateral_coverage_x"].iloc[0]) if len(snap_def) > 0 else 0.5

        # PDP share (upstream only)
        pdp_share_val = 0.0
        if brw["has_reserves"] and len(reserves_q) > 0:
            res_row = reserves_q[
                (reserves_q["borrower_id"] == bid) & (reserves_q["scenario_id"] == scenario_id)
            ]
            if len(res_row) > 0:
                latest = res_row.iloc[-1]
                proved = float(latest["proved_reserves_mmboe"])
                pdp    = float(latest["pdp_mmboe"])
                pdp_share_val = pdp / max(proved, 1e-3)

        # Macro at default date
        mo = macro.loc[def_date] if def_date in macro.index else macro.iloc[-1]
        bbb_spr = float(mo["bbb_spread_bps"])
        z_bbb = (bbb_spr - 150.0) / 50.0

        # Decommissioning burden
        decomm = float(brw.get("decomm_prov_undisc_init_usd_m", 0))
        # Proxy EBITDA from revenue*margin
        ebitda_proxy = float(brw["revenue_init_usd_m"]) * float(brw["ebitda_margin_init"]) * 4
        decomm_burden = decomm / max(ebitda_proxy, 1.0)

        # Hedge coverage at default
        hedge = float(brw["hedge_ratio"])

        # Resolution time z-score
        z_res = (resolution_months - 18.0) / 10.0

        # Industry default rate (simplified)
        idr = 0.03   # approximate

        # RR model
        seniority_secured_flag = 1.0 if seniority == "senior_secured" else 0.0

        logit_rr = (
            _GAMMA["intercept"]
            + _GAMMA["collateral_coverage"] * min(coll_cov, 3.0)
            + _GAMMA["seniority_secured"]   * seniority_secured_flag
            + _GAMMA["pdp_share"]           * pdp_share_val
            + _GAMMA["hedge_coverage"]      * hedge
            + _GAMMA["decomm_burden"]       * min(decomm_burden, 3.0)
            + _GAMMA["bbb_spread_z"]        * z_bbb
            + _GAMMA["industry_default_rate"] * idr * 10
            + _GAMMA["resolution_time_z"]   * z_res
            + rng.normal(0, 0.3)            # ω idiosyncratic
        )

        rr = float(np.clip(expit(logit_rr), 0.01, 0.99))

        # Seniority floor/cap
        if seniority == "senior_secured":
            rr = float(np.clip(rr, 0.10, 0.95))
        elif seniority == "senior_unsecured":
            rr = float(np.clip(rr, 0.05, 0.80))
        else:
            rr = float(np.clip(rr, 0.01, 0.60))

        lgd = 1.0 - rr

        # Gross recovery
        gross_recovery = ead * rr
        workout_cost = gross_recovery * rng.uniform(0.05, 0.15)
        net_recovery = gross_recovery - workout_cost

        # Distribute cash flows over resolution period
        resolution_end = def_date + pd.DateOffset(months=resolution_months)
        recovery_months = pd.date_range(
            def_date + pd.DateOffset(months=1),
            resolution_end,
            freq="ME",
        )

        # Recovery profile: back-loaded (more likely near resolution end)
        n_rec = len(recovery_months)
        if n_rec == 0:
            continue

        weights = np.linspace(0.5, 2.0, n_rec)
        weights /= weights.sum()
        monthly_net = net_recovery * weights
        monthly_gross = gross_recovery * weights
        monthly_cost  = workout_cost * weights

        discount_rate_bps = 1000.0   # 10% discount rate

        for m_idx, rec_date in enumerate(recovery_months):
            rows.append({
                "default_id":                  def_row["default_id"],
                "facility_id":                 fid,
                "borrower_id":                 bid,
                "scenario_id":                 scenario_id,
                "recovery_date":               rec_date,
                "gross_recovery_usd_m":        float(monthly_gross[m_idx]),
                "workout_cost_usd_m":          float(monthly_cost[m_idx]),
                "net_recovery_usd_m":          float(monthly_net[m_idx]),
                "discount_rate_bps":           float(discount_rate_bps),
                "collateral_realisation_source": _coll_source(fac["collateral_type"]),
                "resolution_status":           "ongoing" if m_idx < n_rec - 1 else "resolved",
                "final_lgd":                   float(lgd) if m_idx == n_rec - 1 else float("nan"),
            })

    return pd.DataFrame(rows)


def _coll_source(collateral_type) -> str:
    mapping = {
        "proved_reserves":      "reserve_sale",
        "general_assets":       "asset_sale",
        "commodity_receivables":"receivable_collection",
    }
    return mapping.get(str(collateral_type), "unsecured_recovery")
