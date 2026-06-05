"""
Controlled data-quality noise injection.

Mimics realistic data imperfections in energy credit portfolios:
  - Late quarterly filings (private names)
  - Reserve report delays (after price shocks)
  - Partial hedge disclosure
  - Unit conversion outliers in production rows
  - Duplicate transactions (0.02–0.10%)
  - Restatement flags (1–3% of financial histories)
  - Stale ratings (2–5%)
  - Collateral valuation noise (5–10%)
"""
import numpy as np
import pandas as pd


def inject_noise(
    borrowers: pd.DataFrame,
    facilities: pd.DataFrame,
    fin_q: pd.DataFrame,
    ops_m: pd.DataFrame,
    reserves_q: pd.DataFrame,
    hedges_m: pd.DataFrame,
    snapshots: pd.DataFrame,
    ratings_m: pd.DataFrame,
    rng: np.random.Generator,
) -> dict[str, pd.DataFrame]:
    """Apply all noise layers and return modified tables in a dict."""

    fin_q      = _late_filings(fin_q, borrowers, rng)
    reserves_q = _reserve_report_delays(reserves_q, ops_m, rng)
    hedges_m   = _partial_hedge_disclosure(hedges_m, borrowers, rng)
    ops_m      = _unit_conversion_outliers(ops_m, rng)
    fin_q      = _restatement_flags(fin_q, rng)
    ratings_m  = _stale_ratings(ratings_m, borrowers, rng)
    snapshots  = _collateral_noise(snapshots, rng)
    txn        = _generate_transactions(snapshots, rng)

    return {
        "borrower_financials_q":  fin_q,
        "borrower_operations_m":  ops_m,
        "reserves_q":             reserves_q,
        "hedge_position_m":       hedges_m,
        "facility_snapshot_m":    snapshots,
        "rating_history_m":       ratings_m,
        "transaction_fact":       txn,
    }


def _late_filings(fin_q: pd.DataFrame, borrowers: pd.DataFrame,
                  rng: np.random.Generator) -> pd.DataFrame:
    """Null out 3-8% of financial rows for private names (simulate late filing)."""
    private_ids = set(borrowers[borrowers["ownership_type"] == "private"]["borrower_id"])
    private_mask = fin_q["borrower_id"].isin(private_ids)
    late_mask = private_mask & (rng.random(len(fin_q)) < rng.uniform(0.03, 0.08))

    cols_to_null = [
        "revenue_usd_m", "ebitda_usd_m", "ebit_usd_m", "cfo_usd_m",
        "capex_usd_m", "total_assets_usd_m", "total_equity_usd_m",
    ]
    fin_q = fin_q.copy()
    fin_q.loc[late_mask, cols_to_null] = np.nan
    fin_q.loc[late_mask, "filing_lag_flag"] = True
    if "filing_lag_flag" not in fin_q.columns:
        fin_q["filing_lag_flag"] = False
    else:
        fin_q["filing_lag_flag"] = fin_q["filing_lag_flag"].fillna(False).infer_objects(copy=False)
    return fin_q


def _reserve_report_delays(reserves_q: pd.DataFrame, ops_m: pd.DataFrame,
                            rng: np.random.Generator) -> pd.DataFrame:
    """Null independent_engineer_flag for 5-10% of upstream quarter-ends."""
    if len(reserves_q) == 0:
        return reserves_q
    reserves_q = reserves_q.copy()
    delay_mask = rng.random(len(reserves_q)) < rng.uniform(0.05, 0.10)
    reserves_q.loc[delay_mask, "independent_engineer_flag"] = False
    reserves_q.loc[delay_mask, "engineer_report_date"] = pd.NaT
    reserves_q["reserve_report_delay_flag"] = delay_mask
    return reserves_q


def _partial_hedge_disclosure(hedges_m: pd.DataFrame, borrowers: pd.DataFrame,
                               rng: np.random.Generator) -> pd.DataFrame:
    """Set floors/caps to NaN for 10-20% of smaller borrower hedge rows."""
    if len(hedges_m) == 0:
        return hedges_m
    small_priv = set(
        borrowers[
            ~borrowers["listed_flag"] &
            (borrowers["revenue_init_usd_m"] < 5000)
        ]["borrower_id"]
    )
    hedges_m = hedges_m.copy()
    mask = hedges_m["borrower_id"].isin(small_priv) & (rng.random(len(hedges_m)) < 0.15)
    hedges_m.loc[mask, ["floor_price", "cap_price"]] = np.nan
    return hedges_m


def _unit_conversion_outliers(ops_m: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Inject 0.1-0.3% of rows with boe/bbl/mcf unit confusion (×5.615 factor)."""
    ops_m = ops_m.copy()
    n = len(ops_m)
    outlier_mask = rng.random(n) < rng.uniform(0.001, 0.003)
    # Multiply production by 5.615 (mcf to boe conversion factor) in error
    ops_m.loc[outlier_mask, "total_prod_kboed"] = (
        ops_m.loc[outlier_mask, "total_prod_kboed"] * 5.615
    )
    ops_m["unit_conversion_suspect"] = outlier_mask
    return ops_m


def _restatement_flags(fin_q: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Flag 1-3% of borrower financial histories as containing a restatement."""
    fin_q = fin_q.copy()
    borrower_ids = fin_q["borrower_id"].unique()
    restate_ids = set(
        rng.choice(borrower_ids, size=max(1, int(len(borrower_ids) * 0.02)), replace=False)
    )
    # For restated borrowers, flag one random quarter
    restate_rows = []
    for bid in restate_ids:
        sub = fin_q[fin_q["borrower_id"] == bid]
        if len(sub) == 0:
            continue
        idx = rng.integers(0, len(sub))
        restate_rows.append(sub.index[idx])

    fin_q["restatement_flag"] = False
    fin_q.loc[restate_rows, "restatement_flag"] = True
    return fin_q


def _stale_ratings(ratings_m: pd.DataFrame, borrowers: pd.DataFrame,
                   rng: np.random.Generator) -> pd.DataFrame:
    """For 2-5% of unlisted borrowers, freeze external rating for 3-6 months."""
    ratings_m = ratings_m.copy()
    unlisted = set(borrowers[~borrowers["listed_flag"]]["borrower_id"])
    stale_ids = set(
        rng.choice(list(unlisted), size=max(1, int(len(unlisted) * 0.035)), replace=False)
    )
    for bid in stale_ids:
        mask = ratings_m["borrower_id"] == bid
        sub = ratings_m[mask].sort_values("as_of_month")
        if len(sub) < 6:
            continue
        freeze_start = int(rng.integers(0, len(sub) - 3))
        freeze_len   = int(rng.integers(3, 7))
        freeze_end   = min(freeze_start + freeze_len, len(sub) - 1)
        frozen_rating = sub.iloc[freeze_start]["external_rating"]
        idxs = sub.index[freeze_start:freeze_end + 1]
        ratings_m.loc[idxs, "external_rating"] = frozen_rating
        ratings_m.loc[idxs, "stale_rating_flag"] = True

    if "stale_rating_flag" not in ratings_m.columns:
        ratings_m["stale_rating_flag"] = False
    else:
        ratings_m["stale_rating_flag"] = ratings_m["stale_rating_flag"].fillna(False)
    return ratings_m


def _collateral_noise(snapshots: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Add 5-10% relative noise to collateral values."""
    snapshots = snapshots.copy()
    mask = snapshots["collateral_value_usd_m"] > 0
    noise = rng.normal(1.0, 0.07, mask.sum())
    snapshots.loc[mask, "collateral_value_usd_m"] = (
        snapshots.loc[mask, "collateral_value_usd_m"] * noise
    ).clip(lower=0.0)
    return snapshots


def _generate_transactions(snapshots: pd.DataFrame,
                            rng: np.random.Generator) -> pd.DataFrame:
    """Generate transaction_fact from monthly drawn amounts (with some duplicates)."""
    if len(snapshots) == 0:
        return pd.DataFrame()

    # Sample ~1 transaction per 10 facility-months
    n_sample = max(1, len(snapshots) // 10)
    sample = snapshots.sample(n=n_sample, random_state=int(rng.integers(1, 1_000_000)))

    txn_types = ["drawdown", "repayment", "interest_payment", "fee_payment", "rollover"]
    probs     = [0.30, 0.30, 0.20, 0.10, 0.10]

    rows = []
    for idx, (_, row) in enumerate(sample.iterrows()):
        txn_type = str(rng.choice(txn_types, p=probs))
        amount = float(row["drawn_usd_m"]) * rng.uniform(0.01, 0.20)
        settle_days = int(rng.integers(0, 4))

        rows.append({
            "txn_id":            f"TXN{idx + 1:09d}",
            "facility_id":       row["facility_id"],
            "borrower_id":       row["borrower_id"],
            "txn_date":          row["as_of_month"],
            "txn_type":          txn_type,
            "amount_usd":        float(amount * 1e6),
            "currency":          "USD",
            "commodity_ref":     None,
            "settlement_status": "settled" if settle_days == 0 else "pending",
            "days_to_settle":    settle_days,
        })

    # Inject 0.05% duplicates
    n_dup = max(1, int(len(rows) * 0.0005))
    dup_idxs = rng.choice(len(rows), size=n_dup, replace=False)
    dup_rows = [rows[i].copy() for i in dup_idxs]
    rows.extend(dup_rows)

    return pd.DataFrame(rows)
