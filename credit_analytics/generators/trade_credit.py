"""
O&G business AR (accounts-receivable) credit module.

trade_credit_terms_m grain: (customer_id, as_of_month)

Covers the commercial credit function:
  - approved and temporary credit limits per customer
  - accounts-receivable ageing buckets (not-due, 1-30, 31-60, 61-90, 90+ DPD)
  - payment terms (days)
  - credit hold and blocked-order flags (triggered by AR ageing + credit quality)
  - risk mitigants: LC, guarantee, credit insurance, collateral

AR volume is driven by an assumed notional delivery of products.
AR ageing is driven by the customer's credit tier + macro stress.
"""
import numpy as np
import pandas as pd


# Credit tier → payment behaviour parameters
_CREDIT_TIERS = {
    "tier_1": {   # AAA–A-: strong investment grade
        "rating_range":       range(0, 7),
        "payment_terms_days": (30, 45),
        "limit_usd_m_range":  (5.0, 50.0),
        "delivery_rate":      (0.08, 0.20),
        "pay_prob_1_30":      (0.92, 0.99),
        "pay_prob_31_60":     (0.75, 0.90),
        "pay_prob_61_90":     (0.40, 0.65),
        "overdue_prob":       0.03,
        "hold_threshold_pct": 0.25,
        "lc_prob":             0.05,
        "guarantee_prob":      0.02,
        "insurance_prob":      0.10,
        "collateral_prob":     0.02,
    },
    "tier_2": {   # BBB+–BBB-: investment grade
        "rating_range":       range(7, 11),
        "payment_terms_days": (30, 60),
        "limit_usd_m_range":  (2.0, 20.0),
        "delivery_rate":      (0.10, 0.25),
        "pay_prob_1_30":      (0.78, 0.92),
        "pay_prob_31_60":     (0.55, 0.75),
        "pay_prob_61_90":     (0.25, 0.50),
        "overdue_prob":       0.08,
        "hold_threshold_pct": 0.20,
        "lc_prob":             0.15,
        "guarantee_prob":      0.08,
        "insurance_prob":      0.20,
        "collateral_prob":     0.05,
    },
    "tier_3": {   # BB+–BB-: sub-investment grade
        "rating_range":       range(11, 14),
        "payment_terms_days": (14, 30),
        "limit_usd_m_range":  (0.5, 8.0),
        "delivery_rate":      (0.12, 0.30),
        "pay_prob_1_30":      (0.55, 0.78),
        "pay_prob_31_60":     (0.30, 0.55),
        "pay_prob_61_90":     (0.10, 0.30),
        "overdue_prob":       0.16,
        "hold_threshold_pct": 0.18,
        "lc_prob":             0.35,
        "guarantee_prob":      0.20,
        "insurance_prob":      0.35,
        "collateral_prob":     0.15,
    },
    "tier_4": {   # B and below: high-risk
        "rating_range":       range(14, 22),
        "payment_terms_days": (7, 14),
        "limit_usd_m_range":  (0.1, 3.0),
        "delivery_rate":      (0.15, 0.40),
        "pay_prob_1_30":      (0.35, 0.60),
        "pay_prob_31_60":     (0.10, 0.35),
        "pay_prob_61_90":     (0.03, 0.15),
        "overdue_prob":       0.28,
        "hold_threshold_pct": 0.15,
        "lc_prob":             0.65,
        "guarantee_prob":      0.40,
        "insurance_prob":      0.50,
        "collateral_prob":     0.35,
    },
}


from ..config import RATING_GRADES


def _get_tier(rating: str) -> str:
    idx = RATING_GRADES.index(rating) if rating in RATING_GRADES else 10
    for tier, p in _CREDIT_TIERS.items():
        if idx in p["rating_range"]:
            return tier
    return "tier_4"


def simulate_trade_credit_monthly(
    customers: pd.DataFrame,
    macro_m: pd.DataFrame,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return trade_credit_terms_m."""

    customers = customers.copy().reset_index(drop=True)
    if len(customers) == 0:
        return pd.DataFrame()

    N = len(customers)
    macro = macro_m[macro_m["scenario_id"] == scenario_id].set_index("as_of_month")

    tiers = customers["external_rating"].apply(_get_tier).values
    tier_params = _CREDIT_TIERS

    lim_lo = np.array([tier_params[t]["limit_usd_m_range"][0] for t in tiers])
    lim_hi = np.array([tier_params[t]["limit_usd_m_range"][1] for t in tiers])
    approved_limit = rng.uniform(lim_lo, lim_hi)

    del_lo = np.array([tier_params[t]["delivery_rate"][0] for t in tiers])
    del_hi = np.array([tier_params[t]["delivery_rate"][1] for t in tiers])
    delivery_rate_base = rng.uniform(del_lo, del_hi)

    pp_1_30_lo  = np.array([tier_params[t]["pay_prob_1_30"][0]  for t in tiers])
    pp_1_30_hi  = np.array([tier_params[t]["pay_prob_1_30"][1]  for t in tiers])
    pp_31_60_lo = np.array([tier_params[t]["pay_prob_31_60"][0] for t in tiers])
    pp_31_60_hi = np.array([tier_params[t]["pay_prob_31_60"][1] for t in tiers])
    pp_61_90_lo = np.array([tier_params[t]["pay_prob_61_90"][0] for t in tiers])
    pp_61_90_hi = np.array([tier_params[t]["pay_prob_61_90"][1] for t in tiers])

    base_overdue = np.array([tier_params[t]["overdue_prob"] for t in tiers])
    hold_thresh  = np.array([tier_params[t]["hold_threshold_pct"] for t in tiers])

    pt_lo = np.array([tier_params[t]["payment_terms_days"][0] for t in tiers])
    pt_hi = np.array([tier_params[t]["payment_terms_days"][1] for t in tiers])
    payment_terms = rng.integers(pt_lo, pt_hi + 1).astype(float)

    lc_flag    = rng.random(N) < np.array([tier_params[t]["lc_prob"]         for t in tiers])
    guar_flag  = rng.random(N) < np.array([tier_params[t]["guarantee_prob"]  for t in tiers])
    ins_flag   = rng.random(N) < np.array([tier_params[t]["insurance_prob"]  for t in tiers])
    coll_flag  = rng.random(N) < np.array([tier_params[t]["collateral_prob"] for t in tiers])
    coll_value = np.where(coll_flag, approved_limit * rng.uniform(0.30, 0.80, N), 0.0)

    # Commodity risk: correlated customers worsen faster when oil prices fall
    commodity_risk = customers["commodity_risk_flag"].values

    ar_not_due = np.zeros(N)
    ar_1_30    = np.zeros(N)
    ar_31_60   = np.zeros(N)
    ar_61_90   = np.zeros(N)
    ar_90_plus = np.zeros(N)
    credit_hold = np.zeros(N, dtype=bool)

    slices = []

    for t, month in enumerate(months):
        mo = macro.loc[month] if month in macro.index else macro.iloc[-1]
        gdp_stress  = max(0, (3.0 - float(mo["global_gdp_yoy"])) / 3.0)
        cred_stress = max(0, (float(mo["bbb_spread_bps"]) - 150.0) / 300.0)
        macro_mult  = 1.0 + 1.5 * gdp_stress + 1.0 * cred_stress

        # Commodity-correlated customers get an extra overdue uplift when oil falls
        brent = float(mo.get("brent_usd_bbl", 75.0))
        commodity_stress = max(0.0, (75.0 - brent) / 75.0)
        macro_mult_commodity = macro_mult + 1.0 * commodity_stress
        effective_macro_mult = np.where(commodity_risk, macro_mult_commodity, macro_mult)

        overdue_rate = np.clip(base_overdue * effective_macro_mult, 0.0, 0.70)

        new_ar = approved_limit * delivery_rate_base * rng.uniform(0.8, 1.2, N)
        new_ar = np.clip(new_ar, 0.0, approved_limit * 0.60)

        pay_prob_1_30  = rng.uniform(pp_1_30_lo,  pp_1_30_hi,  N)
        pay_prob_31_60 = rng.uniform(pp_31_60_lo, pp_31_60_hi, N)
        pay_prob_61_90 = rng.uniform(pp_61_90_lo, pp_61_90_hi, N)

        new_90_plus = ar_90_plus * 0.85 + ar_61_90 * (1 - pay_prob_61_90)
        new_61_90   = ar_31_60  * (1 - pay_prob_31_60)
        new_31_60   = ar_1_30   * (1 - pay_prob_1_30)
        new_1_30    = new_ar * overdue_rate
        new_not_due = new_ar * (1 - overdue_rate)

        ar_90_plus = new_90_plus
        ar_61_90   = new_61_90
        ar_31_60   = new_31_60
        ar_1_30    = new_1_30
        ar_not_due = new_not_due

        total_ar      = ar_not_due + ar_1_30 + ar_31_60 + ar_61_90 + ar_90_plus
        total_overdue = ar_1_30 + ar_31_60 + ar_61_90 + ar_90_plus

        new_hold = (total_overdue / np.maximum(approved_limit, 1.0)) > hold_thresh
        cured    = credit_hold & (
            (total_overdue / np.maximum(approved_limit, 1.0)) < hold_thresh * 0.5
        )
        credit_hold = new_hold | (credit_hold & ~cured)

        blocked_order = (ar_90_plus / np.maximum(approved_limit, 1.0)) > 0.10

        temp_boost = np.where(
            rng.random(N) < 0.05,
            approved_limit * rng.uniform(0.10, 0.30, N),
            0.0,
        )
        temp_limit = approved_limit + temp_boost

        review_due = pd.Timestamp(months[0]) + pd.DateOffset(
            months=int(((t + 12) // 12) * 12)
        )

        df = pd.DataFrame({
            "customer_id":                   customers["customer_id"].values,
            "as_of_month":                   month,
            "scenario_id":                   scenario_id,
            "payment_terms_days":            payment_terms,
            "approved_credit_limit_usd_m":   approved_limit,
            "temporary_credit_limit_usd_m":  temp_limit,
            "current_ar_usd_m":              total_ar,
            "ar_not_due_usd_m":              ar_not_due,
            "ar_1_30_dpd_usd_m":             ar_1_30,
            "ar_31_60_dpd_usd_m":            ar_31_60,
            "ar_61_90_dpd_usd_m":            ar_61_90,
            "ar_90_plus_dpd_usd_m":          ar_90_plus,
            "utilisation_pct":               np.clip(
                total_ar / np.maximum(approved_limit, 1.0) * 100, 0, 200
            ),
            "blocked_order_flag":            blocked_order,
            "credit_hold_flag":              credit_hold,
            "letter_of_credit_flag":         lc_flag,
            "guarantee_flag":                guar_flag,
            "credit_insurance_flag":         ins_flag,
            "collateral_required_flag":      coll_flag,
            "collateral_value_usd_m":        coll_value,
            "last_credit_review_date":       months[max(0, t - (t % 12))],
            "next_review_due_date":          review_due,
        })
        slices.append(df)

    return pd.concat(slices, ignore_index=True)
