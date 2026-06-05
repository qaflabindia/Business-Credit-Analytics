"""
Memory-efficient rating history generator.

Processes one month at a time: for each of the M months, computes PD
and ratings for all N borrowers in a single vectorised batch (N × few cols),
accumulates results as a list of small DataFrames, then concatenates once.

Peak memory ≈ N × 30 columns × 8 bytes ≈ a few MB per month.

PD equation (from spec):
  logit(PD1Y) = α_segment
              + 0.85*z(Leverage) - 0.95*z(ICR) - 0.50*z(CashRatio)
              + 0.25*z(DecommBurden) - 0.20*z(ReserveLife)
              - 0.30*HedgeRatio - 0.40*CovenantHeadroom
              + 0.50*z(BBBspread) - 0.55*z(GDP)
              - 0.80*BetaCommodity * z(Brent)
              + borrower_re + time_re
"""
import numpy as np
import pandas as pd
from scipy.special import expit

from ..config import RATING_GRADES, RATING_TO_PD


# PD → rating grade lookup (vectorised)
_LOG_PD_THRESH = np.log([RATING_TO_PD[g] for g in RATING_GRADES])


def _pd_to_grade_idx(log_pd_arr: np.ndarray) -> np.ndarray:
    """Map array of log(PD) values → nearest rating grade index."""
    diff = np.abs(log_pd_arr[:, None] - _LOG_PD_THRESH[None, :])
    return diff.argmin(axis=1)


def _nearest_qend(m: pd.Timestamp) -> pd.Timestamp:
    y, mo = m.year, m.month
    for q in [12, 9, 6, 3]:
        if mo >= q:
            return pd.Timestamp(year=y, month=q, day=1) + pd.offsets.MonthEnd(0)
    return pd.Timestamp(year=y - 1, month=12, day=31)


def update_ratings(
    borrowers: pd.DataFrame,
    fin_q: pd.DataFrame,
    cov_tests: pd.DataFrame,    # accepted but not used per-row (population headroom)
    macro_m: pd.DataFrame,
    months: pd.DatetimeIndex,
    quarters: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return rating_history_m — one row per (borrower_id, as_of_month)."""

    N = len(borrowers)

    # ── Borrower static arrays (N,) ──────────────────────────────────────────
    alpha_pd    = borrowers["alpha_pd"].values.astype(float)
    hedge       = borrowers["hedge_ratio"].values.astype(float)
    b_comm      = borrowers["beta_commodity"].values.astype(float)
    res_life_0  = borrowers["reserve_life_init"].fillna(0.0).values.astype(float)
    listed      = borrowers["listed_flag"].values.astype(bool)
    bid_arr     = borrowers["borrower_id"].values

    # Persistent borrower random effect
    re_brw = rng.normal(0, 0.40, N)

    # ── Pre-index financial data ──────────────────────────────────────────────
    fin_sub = fin_q[fin_q["scenario_id"] == scenario_id].set_index(
        ["borrower_id", "as_of_quarter"]
    )[["net_debt_ebitda_x", "interest_coverage_x", "cash_ratio",
       "decommissioning_prov_disc_usd_m", "ebitda_usd_m"]]

    # ── Pre-index macro data ──────────────────────────────────────────────────
    macro_sub = macro_m[macro_m["scenario_id"] == scenario_id].set_index("as_of_month")

    # ── Inertia state: current grade index per borrower ───────────────────────
    # Initialise from alpha_pd + re
    init_log_pd   = alpha_pd + re_brw   # crude logit → log PD proxy
    init_pd       = np.clip(expit(init_log_pd), 1e-5, 0.999)
    init_grade_idx = _pd_to_grade_idx(np.log(init_pd)).astype(int)
    current_grade  = init_grade_idx.copy()

    # ── Time random effects ───────────────────────────────────────────────────
    re_time = rng.normal(0, 0.15, len(months))

    # ── Loop over months (120 iterations × N vectorised) ─────────────────────
    slices: list[pd.DataFrame] = []

    # Cache last used quarter to avoid repeat lookups
    prev_qdate = None
    lev  = np.full(N, 2.5)
    icr  = np.full(N, 4.0)
    cr   = np.full(N, 0.12)
    decomm = np.zeros(N)
    ebitda = np.full(N, 100.0)

    for t, month in enumerate(months):
        qdate = _nearest_qend(month)

        # Refresh financial state when quarter changes
        if qdate != prev_qdate:
            prev_qdate = qdate
            for i, bid in enumerate(bid_arr):
                key = (bid, qdate)
                if key in fin_sub.index:
                    row = fin_sub.loc[key]
                    lev[i]   = float(row["net_debt_ebitda_x"])
                    icr[i]   = float(row["interest_coverage_x"])
                    cr[i]    = float(row["cash_ratio"])
                    decomm[i]= float(row["decommissioning_prov_disc_usd_m"])
                    ebitda[i]= float(row["ebitda_usd_m"])
                # else: carry forward last known value

        # Macro at this month
        if month in macro_sub.index:
            mo = macro_sub.loc[month]
            bbb_spr = float(mo["bbb_spread_bps"])
            gdp_yoy = float(mo["global_gdp_yoy"])
            brent   = float(mo["brent_usd_bbl"])
        else:
            bbb_spr, gdp_yoy, brent = 150.0, 3.0, 75.0

        # Cross-sectional z-scores (population statistics at this time-step)
        def _z(arr):
            mu, sd = arr.mean(), arr.std()
            return (arr - mu) / max(sd, 1e-3)

        # z-score macro
        z_bbb   = (bbb_spr - 150.0) / 50.0
        z_gdp   = (gdp_yoy - 3.0)  / 1.5
        z_brent = (brent   - 75.0) / 20.0

        # Decomm burden relative to EBITDA
        db = decomm / np.maximum(ebitda * 4, 1.0)

        # PD equation — fully vectorised over N
        logit_pd = (
              alpha_pd
            + 0.85 * _z(lev)
            - 0.95 * _z(icr)
            - 0.50 * _z(cr)
            + 0.25 * _z(np.clip(db, 0, 10))
            - 0.20 * _z(res_life_0)
            - 0.30 * hedge
            - 0.40 * 0.15            # population-average covenant headroom proxy
            + 0.50 * z_bbb
            - 0.55 * z_gdp
            - 0.80 * b_comm * z_brent
            + re_brw
            + re_time[t]
        )

        pd_1y = np.clip(expit(logit_pd), 1e-5, 0.999)

        # Grade from PD (raw)
        raw_idx = _pd_to_grade_idx(np.log(pd_1y)).astype(int)

        # One-notch inertia
        delta = raw_idx - current_grade
        step  = np.sign(delta).astype(int)
        move  = np.minimum(np.abs(delta), 1) * np.where(np.abs(delta) > 0, 1, 0)
        new_grade = np.clip(current_grade + step * move, 0, len(RATING_GRADES) - 1)
        current_grade = new_grade

        # External rating (add stale lag for non-listed)
        noise = rng.normal(0, 0.15, N)
        ext_idx = np.clip(
            _pd_to_grade_idx(np.log(pd_1y) + noise) +
            np.where(~listed, rng.integers(0, 4, N), 0),
            0, len(RATING_GRADES) - 1,
        )

        # Watch: downgraded >1 notch in one month
        watch = (raw_idx > current_grade + 1)

        slices.append(pd.DataFrame({
            "borrower_id":    bid_arr,
            "as_of_month":    month,
            "scenario_id":    scenario_id,
            "agency":         "internal",
            "external_rating":[RATING_GRADES[i] for i in ext_idx],
            "outlook":        np.where(watch, "negative",
                              np.where(raw_idx == current_grade, "stable", "positive")),
            "watch_flag":     watch,
            "internal_grade": [RATING_GRADES[i] for i in new_grade],
            "internal_pd_1y": pd_1y,
            "stale_rating_flag": False,
        }))

    return pd.concat(slices, ignore_index=True)
