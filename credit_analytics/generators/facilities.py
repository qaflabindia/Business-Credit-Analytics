"""
Facility dimension and covenant definition tables.

Produces:
  facility_dim        — one row per facility
  covenant_def_dim    — one-to-many rows per facility
"""
import numpy as np
import pandas as pd

from ..config import SEGMENTS, SENIORITY_LEVELS


_FACILITY_TYPE_PARAMS = {
    "RBL": {
        "seniority": "senior_secured",
        "secured": True,
        "collateral": "proved_reserves",
        "borrowing_base_flag": True,
        "commitment_rev_multiple_range": (0.3, 0.6),
        "spread_bps_range": (200, 350),
        "maturity_years_range": (5, 7),
        "rate_type": "floating",
        "benchmark": "SOFR",
        "covenants": ["leverage", "interest_cover", "borrowing_base", "liquidity"],
    },
    "RCF": {
        "seniority": "senior_secured",
        "secured": True,
        "collateral": "general_assets",
        "borrowing_base_flag": False,
        "commitment_rev_multiple_range": (0.1, 0.4),
        "spread_bps_range": (120, 280),
        "maturity_years_range": (3, 5),
        "rate_type": "floating",
        "benchmark": "SOFR",
        "covenants": ["leverage", "interest_cover", "liquidity"],
    },
    "term_loan": {
        "seniority": "senior_secured",
        "secured": True,
        "collateral": "general_assets",
        "borrowing_base_flag": False,
        "commitment_rev_multiple_range": (0.15, 0.50),
        "spread_bps_range": (150, 320),
        "maturity_years_range": (5, 8),
        "rate_type": "floating",
        "benchmark": "SOFR",
        "covenants": ["leverage", "interest_cover"],
    },
    "bond": {
        "seniority": "senior_unsecured",
        "secured": False,
        "collateral": None,
        "borrowing_base_flag": False,
        "commitment_rev_multiple_range": (0.10, 0.45),
        "spread_bps_range": (80, 250),
        "maturity_years_range": (5, 12),
        "rate_type": "fixed",
        "benchmark": "UST",
        "covenants": ["leverage"],
    },
    "trade_finance": {
        "seniority": "senior_secured",
        "secured": True,
        "collateral": "commodity_receivables",
        "borrowing_base_flag": False,
        "commitment_rev_multiple_range": (0.02, 0.12),
        "spread_bps_range": (100, 220),
        "maturity_years_range": (1, 2),
        "rate_type": "floating",
        "benchmark": "SOFR",
        "covenants": ["liquidity"],
    },
}

_COV_PARAMS = {
    "leverage": {
        "test_name": "net_debt_ebitda",
        "test_formula": "net_debt / ebitda_ltm",
        "threshold_operator": "<=",
        "frequency": "quarterly",
        "cure_days": 30,
        "waiver_allowed": True,
    },
    "interest_cover": {
        "test_name": "ebitda_interest",
        "test_formula": "ebitda_ltm / interest_expense_ltm",
        "threshold_operator": ">=",
        "frequency": "quarterly",
        "cure_days": 30,
        "waiver_allowed": True,
    },
    "borrowing_base": {
        "test_name": "drawn_vs_borrowing_base",
        "test_formula": "drawn_usd_m / borrowing_base_usd_m",
        "threshold_operator": "<=",
        "frequency": "semi_annual",
        "cure_days": 45,
        "waiver_allowed": False,
    },
    "liquidity": {
        "test_name": "minimum_liquidity",
        "test_formula": "cash_usd_m / forecast_debt_service_6m_usd_m",
        "threshold_operator": ">=",
        "frequency": "monthly",
        "cure_days": 15,
        "waiver_allowed": True,
    },
}


def _leverage_threshold(segment: str, facility_type: str) -> float:
    thresholds = {
        "supermajor": 2.0,
        "large_integrated": 2.5,
        "independent_upstream": 3.5,
        "midstream_lng": 5.0,
        "refining_marketing": 3.0,
        "oilfield_services": 3.5,
        "trading_petrochemicals": 3.0,
    }
    return thresholds.get(segment, 3.5)


def generate_facilities(
    borrowers: pd.DataFrame,
    rng: np.random.Generator,
    start_date: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return (facility_dim, covenant_def_dim).

    Commitment sizes are calibrated to borrower revenue and leverage so that:
      total drawn ≈ leverage * EBITDA ≈ leverage * revenue * margin
    """
    start_pd = pd.Timestamp(start_date)
    fac_rows = []
    cov_rows = []
    fac_counter = 0
    cov_counter = 0

    for _, brw in borrowers.iterrows():
        seg = brw["segment"]
        sp = SEGMENTS[seg]

        lo, hi = sp["facilities_per_borrower"]
        n_fac = int(rng.integers(lo, hi + 1))
        fac_types_pool = sp["facility_types"]
        chosen_types = list(rng.choice(fac_types_pool, size=n_fac, replace=True))

        # Ensure at least one RBL if borrower has reserves
        if brw["has_reserves"] and "RBL" in fac_types_pool and "RBL" not in chosen_types:
            chosen_types[0] = "RBL"

        for ftype in chosen_types:
            fac_counter += 1
            fp = _FACILITY_TYPE_PARAMS[ftype]
            mul_lo, mul_hi = fp["commitment_rev_multiple_range"]
            commitment = float(brw["revenue_init_usd_m"] * rng.uniform(mul_lo, mul_hi))
            spread_bps = float(rng.integers(*fp["spread_bps_range"]))
            mat_years = int(rng.integers(*fp["maturity_years_range"]))
            orig_date = start_pd - pd.DateOffset(months=int(rng.integers(0, 24)))
            mat_date = orig_date + pd.DateOffset(years=mat_years)

            fac_id = f"FAC{fac_counter:07d}"

            fac_rows.append({
                "facility_id":          fac_id,
                "borrower_id":          brw["borrower_id"],
                "facility_type":        ftype,
                "currency":             "USD",
                "secured_flag":         fp["secured"],
                "seniority":            fp["seniority"],
                "origination_date":     orig_date,
                "maturity_date":        mat_date,
                "commitment_usd_m":     commitment,
                "spread_bps":           spread_bps,
                "rate_type":            fp["rate_type"],
                "benchmark":            fp["benchmark"],
                "collateral_type":      fp["collateral"],
                "borrowing_base_flag":  fp["borrowing_base_flag"],
                "guarantor_id":         None,
            })

            # Covenants for this facility
            lev_thresh = _leverage_threshold(seg, ftype)
            cov_thresholds = {
                "leverage":       lev_thresh,
                "interest_cover": 3.0 if seg in ("supermajor", "large_integrated") else 2.5,
                "borrowing_base": 1.0,
                "liquidity":      1.0,
            }

            for cname in fp["covenants"]:
                cov_counter += 1
                cp = _COV_PARAMS[cname]
                cov_rows.append({
                    "covenant_id":        f"COV{cov_counter:08d}",
                    "facility_id":        fac_id,
                    "test_name":          cp["test_name"],
                    "test_formula":       cp["test_formula"],
                    "threshold_operator": cp["threshold_operator"],
                    "threshold_value":    cov_thresholds[cname],
                    "frequency":          cp["frequency"],
                    "cure_days":          cp["cure_days"],
                    "waiver_allowed_flag": cp["waiver_allowed"],
                })

    return pd.DataFrame(fac_rows), pd.DataFrame(cov_rows)
