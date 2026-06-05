"""
Quarterly reserves table using proved-reserves stock-flow identity.

ProvedReserves_q = ProvedReserves_q-1
                 - Production_q
                 + Extensions & Discoveries
                 + Acquisitions / Divestments
                 + Net Revisions
"""
import numpy as np
import pandas as pd


def simulate_reserves_quarterly(
    borrowers: pd.DataFrame,
    ops_m: pd.DataFrame,
    fin_q: pd.DataFrame,
    quarters: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return reserves_q for upstream-segment borrowers."""
    # Only keep upstream borrowers
    upstream = borrowers[borrowers["has_reserves"]].copy().reset_index(drop=True)
    if len(upstream) == 0:
        return pd.DataFrame()

    N = len(upstream)
    Q = len(quarters)

    # Initial proved reserves (mmboe): ReserveLife * annual production
    init_prod_kboed = ops_m[
        (ops_m["scenario_id"] == scenario_id) & (ops_m["as_of_month"] == ops_m["as_of_month"].min())
    ].set_index("borrower_id")["total_prod_kboed"].reindex(upstream["borrower_id"]).fillna(10.0).values

    annual_prod_mmboe = init_prod_kboed * 365 / 1e3  # kboed → mmboe pa
    reserve_life_init = upstream["reserve_life_init"].fillna(7.0).values
    proved_reserves = annual_prod_mmboe * reserve_life_init          # (N,)
    proved_reserves = np.maximum(proved_reserves, 1.0)

    # PDP share (pressure-depletion proved): 50-70% of proved
    pdp_share = rng.uniform(0.50, 0.70, N)

    # Offshore share for decommissioning calculation
    offshore_share = upstream["offshore_share"].values

    rows = []
    for q in range(Q):
        qdate = quarters[q]

        # Quarterly production (from ops)
        ops_q = ops_m[
            (ops_m["scenario_id"] == scenario_id) &
            (ops_m["as_of_month"].dt.month.isin([qdate.month])) &
            (ops_m["as_of_month"].dt.year == qdate.year)
        ].set_index("borrower_id")["total_prod_kboed"].reindex(upstream["borrower_id"]).fillna(0.0).values

        quarterly_prod_mmboe = ops_q * 91 / 1e3  # kboed * 91 days → mmboe

        # Extensions and Discoveries (E&D) — driven by capex
        fin_row = fin_q[
            (fin_q["scenario_id"] == scenario_id) &
            (fin_q["as_of_quarter"] == qdate)
        ].set_index("borrower_id")
        capex_q = fin_row["capex_usd_m"].reindex(upstream["borrower_id"]).fillna(0.0).values

        # F&D cost proxy: $15-25/boe
        fnd_cost = rng.uniform(15, 25, N)
        extensions = np.maximum(capex_q / np.maximum(fnd_cost, 1.0) / 4.0, 0)  # quarterly

        # Acquisitions / Divestments (random, sparse)
        acq_div = np.where(rng.random(N) < 0.02, rng.normal(0, 5, N), 0.0)

        # Net Revisions (price-driven + random)
        brent_q = _get_brent(fin_row)
        revision_factor = 0.05 * (brent_q / 75.0 - 1.0)  # revision driven by price vs baseline
        net_revisions = proved_reserves * revision_factor * rng.uniform(0.5, 1.5, N)
        net_revisions += rng.normal(0, 2, N)

        # Stock-flow update
        proved_reserves = np.maximum(
            proved_reserves - quarterly_prod_mmboe + extensions + acq_div + net_revisions,
            0.5,
        )

        # Reserve life and reserve replacement ratio
        annual_prod_curr = quarterly_prod_mmboe * 4
        reserve_life = np.where(annual_prod_curr > 0, proved_reserves / annual_prod_curr, 0.0)
        rrr = np.where(quarterly_prod_mmboe > 0,
                       (extensions + acq_div + net_revisions) / np.maximum(quarterly_prod_mmboe, 1e-3),
                       0.0)

        # PDP / PDNP / PUD split (approximation)
        pdp = proved_reserves * pdp_share
        pdnp = proved_reserves * rng.uniform(0.05, 0.15, N)
        pud = proved_reserves - pdp - pdnp
        pud = np.maximum(pud, 0.0)

        # Mature field share proxy
        mature_share = upstream["mature_asset_share"].values * (1 + 0.02 * q / Q)
        mature_share = np.clip(mature_share, 0.0, 1.0)

        # Independent engineer report (semi-annual, some delays)
        ind_eng = (qdate.month in [6, 12])
        if ind_eng:
            ind_eng_flags = rng.random(N) > 0.08   # 8% delay rate
        else:
            ind_eng_flags = np.zeros(N, dtype=bool)

        for i in range(N):
            rows.append({
                "borrower_id":              upstream.iloc[i]["borrower_id"],
                "as_of_quarter":            qdate,
                "scenario_id":              scenario_id,
                "proved_reserves_mmboe":    float(proved_reserves[i]),
                "pdp_mmboe":                float(pdp[i]),
                "pdnp_mmboe":               float(pdnp[i]),
                "pud_mmboe":                float(pud[i]),
                "reserve_life_years":       float(np.clip(reserve_life[i], 0.0, 30.0)),
                "rrr_pct":                  float(np.clip(rrr[i] * 100, -200, 500)),
                "reserve_revision_mmboe":   float(net_revisions[i]),
                "offshore_share_pct":       float(offshore_share[i] * 100),
                "mature_asset_share_pct":   float(mature_share[i] * 100),
                "engineer_report_date":     qdate if ind_eng else None,
                "independent_engineer_flag": bool(ind_eng_flags[i]),
            })

    return pd.DataFrame(rows)


def _get_brent(fin_row: pd.DataFrame) -> float:
    """Try to extract brent from fin_row; fallback to 75."""
    try:
        return float(fin_row["brent_usd_bbl"].mean()) if "brent_usd_bbl" in fin_row else 75.0
    except Exception:
        return 75.0
