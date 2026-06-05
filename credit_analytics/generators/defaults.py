"""
Vectorized default event simulator.

MonthlyHazard_i,t = 1 - exp(-PD1Y_i,t / 12)
Default_i,t ~ Bernoulli(MonthlyHazard) for non-defaulted borrowers.
Once defaulted, borrower is in resolution for 24 months then eligible again.
"""
import numpy as np
import pandas as pd


def simulate_defaults(
    borrowers: pd.DataFrame,
    ratings_m: pd.DataFrame,
    snapshots: pd.DataFrame,
    cov_tests: pd.DataFrame,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return default_event_fact."""

    rat_sub = ratings_m[ratings_m["scenario_id"] == scenario_id][
        ["borrower_id", "as_of_month", "internal_pd_1y"]
    ].copy()

    snap_sub = snapshots[snapshots["scenario_id"] == scenario_id][
        ["borrower_id", "facility_id", "as_of_month", "ead_usd_m", "dpd_days"]
    ].copy()

    # Aggregate DPD to borrower level (max across facilities)
    dpd_brw = snap_sub.groupby(["borrower_id", "as_of_month"])["dpd_days"].max().reset_index()
    dpd_brw.columns = ["borrower_id", "as_of_month", "max_dpd"]

    # Merge PD and DPD
    panel = rat_sub.merge(dpd_brw, on=["borrower_id", "as_of_month"], how="left")
    panel["max_dpd"] = panel["max_dpd"].fillna(0).astype(int)
    panel = panel.sort_values(["borrower_id", "as_of_month"])

    # Monthly hazard
    panel["hazard"] = 1.0 - np.exp(-panel["internal_pd_1y"] / 12.0)

    # DPD uplift
    panel["hazard"] = np.where(
        panel["max_dpd"] >= 90, 1.0,
        np.where(
            panel["max_dpd"] >= 60, (panel["hazard"] * 2.0).clip(upper=1.0),
            np.where(
                panel["max_dpd"] >= 30, (panel["hazard"] * 1.5).clip(upper=1.0),
                panel["hazard"],
            ),
        ),
    )

    # Draw Bernoulli events
    panel["_draw"] = rng.random(len(panel))
    panel["_triggered"] = (panel["max_dpd"] >= 90) | (panel["_draw"] < panel["hazard"])

    # Enforce 24-month resolution window: no re-default within 24m
    default_rows = []
    def_counter = [0]
    resolution_end: dict[str, pd.Timestamp] = {}

    # Sort panel for sequential processing
    panel_sorted = panel.sort_values(["borrower_id", "as_of_month"]).copy()

    for _, row in panel_sorted[panel_sorted["_triggered"]].iterrows():
        bid   = row["borrower_id"]
        month = pd.Timestamp(row["as_of_month"])

        # Skip if in resolution
        if bid in resolution_end and month < resolution_end[bid]:
            continue

        def_counter[0] += 1
        did = f"DEF{def_counter[0]:07d}"

        resolution_end[bid] = month + pd.DateOffset(months=24)

        dpd = int(row["max_dpd"])
        pd_val = float(row["internal_pd_1y"])

        if dpd >= 90:
            d_type = "dpd_90"
            dpd_90f, utpf, bkf, drf = True, False, False, False
        elif rng.random() < 0.30:
            d_type = "bankruptcy"
            dpd_90f, utpf, bkf, drf = False, True, True, False
        elif rng.random() < 0.40:
            d_type = "distressed_restructuring"
            dpd_90f, utpf, bkf, drf = False, True, False, True
        else:
            d_type = "unlikely_to_pay"
            dpd_90f, utpf, bkf, drf = False, True, False, False

        reason = _reason_code(pd_val, dpd, rng)

        # Per-facility rows
        fac_snap = snap_sub[
            (snap_sub["borrower_id"] == bid) & (snap_sub["as_of_month"] == month)
        ]
        for _, fs in fac_snap.iterrows():
            default_rows.append({
                "default_id":                    did,
                "borrower_id":                   bid,
                "facility_id":                   fs["facility_id"],
                "default_date":                  month,
                "scenario_id":                   scenario_id,
                "default_type":                  d_type,
                "dpd_90_flag":                   dpd_90f,
                "utp_flag":                      utpf,
                "bankruptcy_flag":               bkf,
                "distressed_restructuring_flag": drf,
                "reason_code":                   reason,
                "default_ead_usd_m":             float(fs["ead_usd_m"]),
            })

    return pd.DataFrame(default_rows)


def _reason_code(pd_1y: float, dpd: int, rng) -> str:
    candidates = []
    if pd_1y > 0.20:
        candidates.append("high_leverage_risk")
    if dpd >= 30:
        candidates.append("payment_delinquency")
    if not candidates:
        candidates = [
            "liquidity_deterioration",
            "commodity_price_shock",
            "cash_flow_shortfall",
            "refinancing_failure",
            "covenant_breach",
        ]
    return str(rng.choice(candidates))
