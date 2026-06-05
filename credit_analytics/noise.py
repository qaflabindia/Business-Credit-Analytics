"""
Controlled data-quality noise injection for the O&G AR dataset.

Mimics realistic imperfections in commercial credit / receivables data:
  - Late credit reviews (unlisted / small customers)
  - Duplicate invoice postings (0.02–0.05%)
  - AR rounding artefacts (some buckets rounded to nearest 1000)
  - Temporary-limit entries missing on a subset of rows
  - Sanctions / KYC flag staleness
"""
import numpy as np
import pandas as pd


def inject_noise(
    ar_m: pd.DataFrame,
    customers: pd.DataFrame,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Apply all AR noise layers and return the modified DataFrame."""
    ar_m = ar_m.copy()
    ar_m = _late_review_noise(ar_m, customers, rng)
    ar_m = _ar_rounding_artefacts(ar_m, rng)
    ar_m = _missing_temp_limits(ar_m, rng)
    ar_m = _duplicate_rows(ar_m, rng)
    return ar_m


def _late_review_noise(
    ar_m: pd.DataFrame, customers: pd.DataFrame, rng: np.random.Generator
) -> pd.DataFrame:
    """Null out next_review_due_date for ~4% of small / unlisted customers."""
    small_ids = set(
        customers[customers["annual_revenue_est_usd_m"] < 100]["customer_id"]
    )
    mask = ar_m["customer_id"].isin(small_ids) & (rng.random(len(ar_m)) < 0.04)
    ar_m.loc[mask, "next_review_due_date"] = pd.NaT
    ar_m["review_date_missing_flag"] = mask
    return ar_m


def _ar_rounding_artefacts(ar_m: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Round AR bucket values to nearest $1 000 for 8% of rows (manual-entry artefact)."""
    mask = rng.random(len(ar_m)) < 0.08
    for col in ["ar_1_30_dpd_usd_m", "ar_31_60_dpd_usd_m",
                "ar_61_90_dpd_usd_m", "ar_90_plus_dpd_usd_m"]:
        ar_m.loc[mask, col] = (ar_m.loc[mask, col] * 1000).round() / 1000
    return ar_m


def _missing_temp_limits(ar_m: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Set temporary_credit_limit_usd_m to NaN for 3% of rows (not recorded in system)."""
    mask = rng.random(len(ar_m)) < 0.03
    ar_m.loc[mask, "temporary_credit_limit_usd_m"] = np.nan
    return ar_m


def _duplicate_rows(ar_m: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Inject 0.03% duplicate rows (double-posted month-end snapshots)."""
    n_dup = max(1, int(len(ar_m) * 0.0003))
    dup_idx = rng.choice(len(ar_m), size=n_dup, replace=False)
    dups = ar_m.iloc[dup_idx].copy()
    return pd.concat([ar_m, dups], ignore_index=True)
