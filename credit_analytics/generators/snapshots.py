"""
Vectorized monthly facility snapshot generator.

Avoids Python row-level loops by building the (facility × month) panel
via pandas cross-join, then applying all computations with bulk merges
and vectorized numpy operations.
"""
import numpy as np
import pandas as pd


def build_facility_snapshots(
    facilities: pd.DataFrame,
    borrowers: pd.DataFrame,
    fin_q: pd.DataFrame,
    reserves_q: pd.DataFrame,
    macro_m: pd.DataFrame,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return facility_snapshot_m — one row per (facility_id, as_of_month)."""

    # ── 1. Quarter mapping ────────────────────────────────────────────────────
    months_df = pd.DataFrame({"as_of_month": months})
    months_df["as_of_quarter"] = months_df["as_of_month"].apply(_nearest_qend)

    # ── 2. Facility × month cross-join (filter by active dates) ──────────────
    fac = facilities[["facility_id", "borrower_id", "facility_type",
                       "origination_date", "maturity_date",
                       "commitment_usd_m", "spread_bps", "rate_type",
                       "collateral_type", "borrowing_base_flag", "seniority"]].copy()
    fac["origination_date"] = pd.to_datetime(fac["origination_date"])
    fac["maturity_date"]    = pd.to_datetime(fac["maturity_date"])

    # Cross-join: add a constant key then merge
    fac["_key"] = 1
    months_df["_key"] = 1
    panel = fac.merge(months_df, on="_key").drop(columns="_key")

    # Keep only active facility-months
    panel = panel[
        (panel["as_of_month"] >= panel["origination_date"]) &
        (panel["as_of_month"] <= panel["maturity_date"])
    ].copy()

    # ── 3. Attach macro ───────────────────────────────────────────────────────
    macro_sub = macro_m[macro_m["scenario_id"] == scenario_id][
        ["as_of_month", "brent_usd_bbl", "bbb_spread_bps", "policy_rate_bps"]
    ]
    panel = panel.merge(macro_sub, on="as_of_month", how="left")

    # ── 4. Attach quarterly financials ────────────────────────────────────────
    fin_sub = fin_q[fin_q["scenario_id"] == scenario_id][
        ["borrower_id", "as_of_quarter",
         "net_debt_ebitda_x", "interest_coverage_x", "cash_usd_m",
         "total_assets_usd_m", "interest_expense_usd_m"]
    ]
    panel = panel.merge(fin_sub, on=["borrower_id", "as_of_quarter"], how="left")

    # Forward-fill missing quarters
    for col in ["net_debt_ebitda_x", "interest_coverage_x",
                "cash_usd_m", "total_assets_usd_m", "interest_expense_usd_m"]:
        panel[col] = (panel.groupby("facility_id")[col]
                           .transform(lambda s: s.ffill().bfill()))
    panel["net_debt_ebitda_x"]   = panel["net_debt_ebitda_x"].fillna(2.5)
    panel["interest_coverage_x"] = panel["interest_coverage_x"].fillna(4.0)
    panel["cash_usd_m"]          = panel["cash_usd_m"].fillna(50.0)
    panel["total_assets_usd_m"]  = panel["total_assets_usd_m"].fillna(500.0)
    panel["interest_expense_usd_m"] = panel["interest_expense_usd_m"].fillna(10.0)

    # ── 5. Utilisation and drawn ──────────────────────────────────────────────
    util_base = panel["facility_type"].map({
        "RBL": 0.70, "RCF": 0.40, "term_loan": 1.00,
        "bond": 1.00, "trade_finance": 0.60,
    }).fillna(0.50)

    n = len(panel)
    util_noise = rng.normal(0, 0.08, n)
    panel["utilisation_pct"] = np.clip((util_base + util_noise) * 100, 0.0, 100.0)
    # Term loans and bonds fully drawn
    full_draw_mask = panel["facility_type"].isin(["term_loan", "bond"])
    panel.loc[full_draw_mask, "utilisation_pct"] = 100.0

    panel["drawn_usd_m"]   = panel["commitment_usd_m"] * panel["utilisation_pct"] / 100.0
    panel["undrawn_usd_m"] = panel["commitment_usd_m"] - panel["drawn_usd_m"]

    # EAD
    ccf = panel["facility_type"].map({
        "RBL": 0.75, "RCF": 0.75, "term_loan": 0.50,
        "bond": 0.50, "trade_finance": 0.50,
    }).fillna(0.50)
    panel["ead_usd_m"] = panel["drawn_usd_m"] + ccf * panel["undrawn_usd_m"]

    # ── 6. Interest rate ──────────────────────────────────────────────────────
    fixed_mask = panel["rate_type"] == "fixed"
    panel["interest_rate_all_in_bps"] = np.where(
        fixed_mask,
        250.0 + panel["spread_bps"],
        panel["policy_rate_bps"] + panel["spread_bps"],
    )

    # ── 7. Collateral value ───────────────────────────────────────────────────
    coll_noise = rng.normal(1.0, 0.07, n)
    coll_noise = np.clip(coll_noise, 0.70, 1.30)

    # Proved-reserves collateral (RBL)
    rbl_mask = panel["collateral_type"] == "proved_reserves"
    # Simple proxy: 50% of drawn × (brent/75) × noise
    panel["collateral_value_usd_m"] = np.where(
        rbl_mask,
        panel["drawn_usd_m"] * (panel["brent_usd_bbl"] / 75.0) * 0.85 * coll_noise,
        np.where(
            panel["collateral_type"] == "commodity_receivables",
            panel["drawn_usd_m"] * rng.uniform(0.80, 0.95, n),
            np.where(
                panel["collateral_type"].notna(),
                panel["total_assets_usd_m"] * 0.25 * coll_noise,
                0.0,
            ),
        ),
    )
    panel["collateral_coverage_x"] = (
        panel["collateral_value_usd_m"] / panel["drawn_usd_m"].clip(lower=1.0)
    )

    # ── 8. Borrowing base (RBL only) ─────────────────────────────────────────
    panel["borrowing_base_usd_m"] = np.where(
        panel["borrowing_base_flag"],
        panel["commitment_usd_m"] * 0.60 * (panel["brent_usd_bbl"] / 75.0),
        float("nan"),
    )

    # ── 9. Financial stress indicator → DPD ──────────────────────────────────
    lev_stress = np.clip((panel["net_debt_ebitda_x"] - 3.0) / 5.0, 0.0, 1.0)
    icr_stress = np.clip((2.5 - panel["interest_coverage_x"]) / 2.5, 0.0, 1.0)
    stress = (lev_stress + icr_stress) / 2.0

    # DPD: probabilistic, driven by stress (simplified — no memory across months)
    miss_prob = np.clip(stress * 0.05, 0.0, 0.05)
    missed = rng.random(n) < miss_prob
    dpd_raw = np.where(missed, rng.choice([30, 60, 90, 120], n), 0)
    panel["dpd_days"] = dpd_raw.astype(int)

    # ── 10. Accrual status and IFRS 9 stage ──────────────────────────────────
    panel["accrual_status"] = np.where(panel["dpd_days"] >= 90, "non_accruing", "accruing")
    panel["stage_ifrs9"] = np.where(
        panel["dpd_days"] >= 90, 3,
        np.where(
            (panel["dpd_days"] >= 30) | (stress > 0.60) |
            (panel["collateral_coverage_x"] < 0.80),
            2, 1,
        ),
    ).astype(int)

    panel["watchlist_flag"] = (
        (panel["stage_ifrs9"] >= 2) | (panel["dpd_days"] > 0)
    )

    # ── 11. Assemble output ───────────────────────────────────────────────────
    out_cols = [
        "facility_id", "borrower_id", "as_of_month",
        "drawn_usd_m", "undrawn_usd_m", "utilisation_pct", "ead_usd_m",
        "interest_rate_all_in_bps", "collateral_value_usd_m",
        "collateral_coverage_x", "borrowing_base_usd_m",
        "dpd_days", "accrual_status", "stage_ifrs9", "watchlist_flag",
    ]
    panel["scenario_id"] = scenario_id
    return panel[out_cols + ["scenario_id"]].reset_index(drop=True)


def _nearest_qend(m: pd.Timestamp) -> pd.Timestamp:
    qm = [3, 6, 9, 12]
    y, mo = m.year, m.month
    for q in reversed(qm):
        if mo >= q:
            return pd.Timestamp(year=y, month=q, day=1) + pd.offsets.MonthEnd(0)
    return pd.Timestamp(year=y - 1, month=12, day=31)
