"""
Vectorized covenant test generator.

Builds the (facility × covenant × quarter) panel via pandas merges,
then evaluates all tests in bulk using vectorized comparisons.
"""
import numpy as np
import pandas as pd


_TEST_SPECS = {
    "net_debt_ebitda": {
        "fin_col":    "net_debt_ebitda_x",
        "direction":  "lower_is_good",   # breach if measured > threshold
        "snap_col":   None,
    },
    "ebitda_interest": {
        "fin_col":    "interest_coverage_x",
        "direction":  "higher_is_good",  # breach if measured < threshold
        "snap_col":   None,
    },
    "drawn_vs_borrowing_base": {
        "fin_col":    None,
        "direction":  "lower_is_good",
        "snap_col":   "drawn_vs_bb",     # computed from snapshots
    },
    "minimum_liquidity": {
        "fin_col":    "liquidity_ratio",  # computed below
        "direction":  "higher_is_good",
        "snap_col":   None,
    },
}


def test_covenants(
    facilities: pd.DataFrame,
    covenant_defs: pd.DataFrame,
    fin_q: pd.DataFrame,
    snapshots: pd.DataFrame,
    quarters: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return covenant_test_fact — one row per (facility, covenant, test_date)."""

    fin_sub = fin_q[fin_q["scenario_id"] == scenario_id][[
        "borrower_id", "as_of_quarter",
        "net_debt_ebitda_x", "interest_coverage_x",
        "cash_usd_m", "interest_expense_usd_m",
    ]].copy()

    snap_sub = snapshots[snapshots["scenario_id"] == scenario_id]

    # Snap quarterly: take the quarter-end month from snapshots
    snap_q = snap_sub[snap_sub["as_of_month"].isin(quarters)][
        ["facility_id", "as_of_month", "drawn_usd_m", "borrowing_base_usd_m"]
    ].rename(columns={"as_of_month": "as_of_quarter"})

    # Compute liquidity ratio in fin_sub
    fin_sub["liquidity_ratio"] = (
        fin_sub["cash_usd_m"] / (fin_sub["interest_expense_usd_m"] * 2).clip(lower=1.0)
    )

    # ── Build (covenant × quarter) panel using explode (avoids large cross-join) ─
    # Attach borrower_id and active date range to each covenant
    cov_fac = covenant_defs.merge(
        facilities[["facility_id", "borrower_id", "origination_date", "maturity_date"]],
        on="facility_id",
    )
    cov_fac["origination_date"] = pd.to_datetime(cov_fac["origination_date"])
    cov_fac["maturity_date"]    = pd.to_datetime(cov_fac["maturity_date"])

    # For each covenant, build list of active quarters (avoids 1M-row cross-join)
    quarters_arr = pd.DatetimeIndex(quarters)

    def _active_quarters(row):
        mask = (quarters_arr >= row["origination_date"]) & (quarters_arr <= row["maturity_date"])
        return quarters_arr[mask].tolist()

    cov_fac = cov_fac.copy()
    cov_fac["as_of_quarter"] = cov_fac.apply(_active_quarters, axis=1)
    # explode already restricts to active quarters; drop date cols to free memory
    panel = cov_fac.explode("as_of_quarter").dropna(subset=["as_of_quarter"])
    panel = panel.drop(columns=["origination_date", "maturity_date"]).copy()
    del cov_fac

    # ── Attach financial data ──────────────────────────────────────────────────
    panel = panel.merge(
        fin_sub[["borrower_id", "as_of_quarter",
                 "net_debt_ebitda_x", "interest_coverage_x", "liquidity_ratio"]],
        on=["borrower_id", "as_of_quarter"],
        how="left",
    )

    # Attach drawn-vs-BB from snapshots
    panel = panel.merge(snap_q, on=["facility_id", "as_of_quarter"], how="left")
    panel["drawn_vs_bb"] = (
        panel["drawn_usd_m"] / panel["borrowing_base_usd_m"].clip(lower=1.0)
    )

    # Fill defaults
    panel["net_debt_ebitda_x"]   = panel["net_debt_ebitda_x"].fillna(2.5)
    panel["interest_coverage_x"] = panel["interest_coverage_x"].fillna(4.0)
    panel["liquidity_ratio"]     = panel["liquidity_ratio"].fillna(1.5)
    panel["drawn_vs_bb"]         = panel["drawn_vs_bb"].fillna(0.6)

    # ── Map test name → measured value ────────────────────────────────────────
    test_to_col = {
        "net_debt_ebitda":        "net_debt_ebitda_x",
        "ebitda_interest":        "interest_coverage_x",
        "drawn_vs_borrowing_base":"drawn_vs_bb",
        "minimum_liquidity":      "liquidity_ratio",
    }
    panel["_measured_col"] = panel["test_name"].map(test_to_col)

    # Build measured_value column dynamically
    panel["measured_value"] = float("nan")
    for tname, col in test_to_col.items():
        mask = panel["test_name"] == tname
        if col in panel.columns:
            panel.loc[mask, "measured_value"] = panel.loc[mask, col]

    # ── Evaluate breach ────────────────────────────────────────────────────────
    lower_good = panel["test_name"].isin(["net_debt_ebitda", "drawn_vs_borrowing_base"])
    panel["breach_flag"] = np.where(
        lower_good,
        panel["measured_value"] > panel["threshold_value"],
        panel["measured_value"] < panel["threshold_value"],
    )

    # Headroom
    panel["headroom_pct"] = np.where(
        lower_good,
        (panel["threshold_value"] - panel["measured_value"])
            / panel["threshold_value"].abs().clip(lower=1e-3) * 100,
        (panel["measured_value"] - panel["threshold_value"])
            / panel["threshold_value"].abs().clip(lower=1e-3) * 100,
    )
    # Add small noise to headroom
    panel["headroom_pct"] += rng.normal(0, 1.5, len(panel))

    # Waiver
    panel["waiver_flag"] = (
        panel["breach_flag"] &
        panel["waiver_allowed_flag"] &
        (rng.random(len(panel)) < 0.30)
    )

    # Cure end date
    panel["cure_end_date"] = pd.NaT
    breach_mask = panel["breach_flag"]
    panel.loc[breach_mask, "cure_end_date"] = (
        panel.loc[breach_mask, "as_of_quarter"] +
        pd.to_timedelta(panel.loc[breach_mask, "cure_days"].astype(int), unit="D")
    )

    # Breach severity
    panel["breach_severity"] = "none"
    panel.loc[breach_mask & (panel["headroom_pct"] < -20), "breach_severity"] = "critical"
    panel.loc[breach_mask & (panel["headroom_pct"] < -10) & (panel["headroom_pct"] >= -20), "breach_severity"] = "material"
    panel.loc[breach_mask & (panel["headroom_pct"] >= -10), "breach_severity"] = "minor"

    out_cols = [
        "facility_id", "covenant_id", "as_of_quarter",
        "measured_value", "headroom_pct", "breach_flag",
        "waiver_flag", "cure_end_date", "breach_severity",
    ]
    panel["scenario_id"] = scenario_id
    return panel[out_cols + ["scenario_id"]].reset_index(drop=True)
