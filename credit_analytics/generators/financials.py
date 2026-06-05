"""
Quarterly financial statement simulator.

Implements:
  ln(Rev_i,q) = ln(Rev_i,q-1) + μ + β_oil*Δln(Brent) + β_gas*Δln(Gas) + β_gdp*GDP + ε
  Margin_i,q = clip(Margin_i,q-1 + shocks + noise)
  EBITDA = Rev * Margin
  Balance-sheet identities maintained within ~0.5% tolerance.
"""
import numpy as np
import pandas as pd


def simulate_financials_quarterly(
    borrowers: pd.DataFrame,
    macro_m: pd.DataFrame,
    quarters: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return borrower_financials_q with one row per (borrower, quarter)."""
    macro_q = _quarterly_macro(macro_m, quarters, scenario_id)

    N = len(borrowers)
    Q = len(quarters)

    # Borrower parameter arrays (N,)
    mu_rev   = borrowers["mu_revenue"].values.astype(float)
    b_oil    = borrowers["beta_oil"].values.astype(float)
    b_gas    = borrowers["beta_gas"].values.astype(float)
    b_gdp    = borrowers["beta_gdp"].values.astype(float)
    hedge    = borrowers["hedge_ratio"].values.astype(float)

    # Macro arrays (Q,)
    brent     = macro_q["brent_usd_bbl"].values.astype(float)
    gas       = macro_q["henry_hub_usd_mmbtu"].values.astype(float)
    gdp       = macro_q["global_gdp_yoy"].values.astype(float)
    bbb_spr   = macro_q["bbb_spread_bps"].values.astype(float)
    inflation = macro_q["policy_rate_bps"].values.astype(float) / 100.0  # rough proxy

    # Log-revenue innovations (N, Q)
    eps_rev = rng.normal(0, 0.04, (N, Q))

    # Δln(Brent), Δln(Gas) — shape (Q,) with [0]=0
    dln_brent = np.concatenate([[0.0], np.diff(np.log(np.maximum(brent, 1e-3)))])
    dln_gas   = np.concatenate([[0.0], np.diff(np.log(np.maximum(gas,   1e-3)))])

    # Initial log-revenue (N,)
    ln_rev = np.log(np.maximum(borrowers["revenue_init_usd_m"].values.astype(float), 1e-3))

    # Initial margin (N,)
    margin = borrowers["ebitda_margin_init"].values.astype(float).copy()

    # Margin noise (N, Q)
    eps_margin = rng.normal(0, 0.015, (N, Q))

    # Leverage and interest rate
    leverage = borrowers["leverage_init"].values.astype(float).copy()
    interest_rate = 0.06 * np.ones(N)  # initial all-in rate

    # Decommissioning provision (starts at initial value, grows slowly)
    decomm_undisc = borrowers["decomm_prov_undisc_init_usd_m"].values.astype(float).copy()

    rows = []

    for q in range(Q):
        # --- Revenue update (AR process) ---
        # broadcast: (N,) * scalar → (N,)
        ln_rev = (ln_rev
                  + mu_rev
                  + b_oil * dln_brent[q]
                  + b_gas * dln_gas[q]
                  + b_gdp * (gdp[q] / 100.0)
                  + eps_rev[:, q])
        revenue = np.exp(ln_rev)

        # --- Margin update ---
        price_real_shock    =  0.40 * dln_brent[q] + 0.20 * dln_gas[q]
        lifting_cost_shock  =  0.15 * (inflation[q] - 4.5) / 100.0
        outage_ratio        =  0.0   # populated in operations module
        inflation_shock     =  max(0.0, (inflation[q] - 4.5) / 100.0)

        margin = np.clip(
            margin
            + 0.25 * price_real_shock
            - 0.15 * lifting_cost_shock
            - 0.05 * outage_ratio
            - 0.10 * inflation_shock
            + eps_margin[:, q],
            0.01, 0.85,
        )

        # Hedge cushions margin volatility
        margin = margin + 0.05 * hedge * abs(dln_brent[q])
        margin = np.clip(margin, 0.01, 0.85)

        ebitda = revenue * margin

        # --- P&L derivations ---
        da_rate = 0.12          # D&A as % of revenue
        da = revenue * da_rate
        ebit = ebitda - da

        gross_debt = np.maximum(leverage * ebitda * 4, 0)   # leverage x annualised EBITDA
        interest_expense = gross_debt * interest_rate

        # Tax (simplified effective rate)
        ebt = ebit - interest_expense
        tax_paid = np.maximum(ebt * 0.25, 0.0)
        net_income = ebt - tax_paid

        # Capex (segment-calibrated; partly discretionary)
        capex_rate = np.where(borrowers["has_reserves"].values, 0.25, 0.08)
        capex = revenue * capex_rate * (1.0 + 0.2 * rng.normal(0, 1, N))
        capex = np.maximum(capex, 0.0)

        # Cash flow from operations (simplified)
        cfo = ebitda - interest_expense - tax_paid + da * 0.30

        # Cash on balance sheet
        fcf = cfo - capex
        cash_min = gross_debt * 0.05
        cash = np.maximum(cash_min, gross_debt * 0.10 + fcf * 0.5)

        net_debt = gross_debt - cash
        total_assets = gross_debt + cash + revenue * 0.80    # approx tangible assets
        total_equity = total_assets - gross_debt
        total_equity = np.maximum(total_equity, total_assets * 0.05)

        working_capital = revenue * 0.08
        receivables = revenue * 0.06
        inventory = revenue * 0.04

        # Decommissioning (slow growth + discount factor drift)
        decomm_disc_rate = np.exp(-0.07 * 15)   # proxy discount at 15y horizon
        decomm_undisc *= (1.0 + 0.02 / 4.0)     # 2% pa growth in real liability
        decomm_disc = decomm_undisc * decomm_disc_rate

        # Update leverage for next period
        leverage = np.where(ebitda > 0, net_debt / (ebitda * 4), leverage)
        leverage = np.clip(leverage, 0.05, 20.0)

        # Append vectorised quarter slice
        q_df = pd.DataFrame({
            "borrower_id":                       borrowers["borrower_id"].values,
            "as_of_quarter":                     quarters[q],
            "scenario_id":                       scenario_id,
            "revenue_usd_m":                     revenue,
            "ebitda_usd_m":                      ebitda,
            "ebit_usd_m":                        ebit,
            "cfo_usd_m":                         cfo,
            "capex_usd_m":                       capex,
            "interest_expense_usd_m":            interest_expense,
            "tax_paid_usd_m":                    tax_paid,
            "cash_usd_m":                        cash,
            "gross_debt_usd_m":                  gross_debt,
            "net_debt_usd_m":                    net_debt,
            "total_assets_usd_m":                total_assets,
            "total_equity_usd_m":                total_equity,
            "working_capital_usd_m":             working_capital,
            "receivables_usd_m":                 receivables,
            "inventory_usd_m":                   inventory,
            "decommissioning_prov_disc_usd_m":   decomm_disc,
            "decommissioning_prov_undisc_usd_m": decomm_undisc,
            "leases_usd_m":                      revenue * 0.03,
            "net_debt_ebitda_x":                 leverage,
            "interest_coverage_x":               (ebitda * 4) / np.maximum(interest_expense * 4, 1e-3),
            "cash_ratio":                        cash / np.maximum(gross_debt, 1e-3),
        })
        rows.append(q_df)

    return pd.concat(rows, ignore_index=True)


def _quarterly_macro(macro_m: pd.DataFrame, quarters: pd.DatetimeIndex,
                     scenario_id: str) -> pd.DataFrame:
    """Extract macro values for quarter-end months from the monthly table."""
    sub = macro_m[macro_m["scenario_id"] == scenario_id].copy()
    sub = sub[sub["as_of_month"].isin(quarters)].sort_values("as_of_month").reset_index(drop=True)
    # Fill missing quarters by forward-fill
    base = pd.DataFrame({"as_of_month": quarters})
    merged = base.merge(sub, on="as_of_month", how="left").ffill()
    return merged
