"""
Commodity trading counterparty credit book.

trading_exposure_m grain: (counterparty_id, commodity, as_of_month)

Covers Shell's trading credit function:
  - gross and net MTM exposure (mark-to-market)
  - settlement exposure (physical delivery receivables)
  - potential future exposure (PFE at 95th percentile)
  - replacement cost (cost to re-execute contract if counterparty defaults)
  - netting agreements reduce gross → net
  - CSA (Credit Support Annex) triggers collateral posting / receipt
  - margin calls when net MTM moves against counterparty
  - wrong-way risk flag (oil-producer exposure rises when oil falls)
  - limit breaches

Commodities traded:
  crude_oil | lng | naphtha | diesel | natural_gas | power | chemicals | bunker_fuel

MTM exposure:
  MTM_positive = max(0, position × (current_price − entry_price) × notional)
  MTM_negative = max(0, position × (entry_price − current_price) × notional)
  Netting: net_exposure = MTM_positive − collateral_received + settlement_exposure

PFE (simplified parametric approach):
  PFE = net_mtm_positive × vol_mult × √(remaining_days/365) × 1.65
  where vol_mult is commodity-specific annualised vol factor
"""
import numpy as np
import pandas as pd


# Commodity-specific parameters
_COMMODITY_PARAMS = {
    "crude_oil": {
        "vol_annual":       0.35,   # annualised price vol
        "settlement_days":  3,      # days from trade to settlement
        "max_tenor_months": 24,
        "price_col":        "brent_usd_bbl",
        "unit":             "bbl",
        "notional_scale_m": 50.0,   # typical notional per trade (USD m)
    },
    "lng": {
        "vol_annual":       0.40,
        "settlement_days":  5,
        "max_tenor_months": 60,
        "price_col":        "jkm_usd_mmbtu",
        "unit":             "mmbtu",
        "notional_scale_m": 80.0,
    },
    "naphtha": {
        "vol_annual":       0.38,
        "settlement_days":  3,
        "max_tenor_months": 12,
        "price_col":        "brent_usd_bbl",
        "unit":             "bbl",
        "notional_scale_m": 30.0,
    },
    "natural_gas": {
        "vol_annual":       0.45,
        "settlement_days":  2,
        "max_tenor_months": 36,
        "price_col":        "henry_hub_usd_mmbtu",
        "unit":             "mmbtu",
        "notional_scale_m": 25.0,
    },
    "diesel": {
        "vol_annual":       0.32,
        "settlement_days":  3,
        "max_tenor_months": 12,
        "price_col":        "brent_usd_bbl",
        "unit":             "bbl",
        "notional_scale_m": 40.0,
    },
    "power": {
        "vol_annual":       0.55,
        "settlement_days":  1,
        "max_tenor_months": 12,
        "price_col":        "ttf_usd_mmbtu",
        "unit":             "mwh",
        "notional_scale_m": 20.0,
    },
    "chemicals": {
        "vol_annual":       0.28,
        "settlement_days":  5,
        "max_tenor_months": 12,
        "price_col":        "brent_usd_bbl",
        "unit":             "tonne",
        "notional_scale_m": 15.0,
    },
    "bunker_fuel": {
        "vol_annual":       0.33,
        "settlement_days":  3,
        "max_tenor_months": 6,
        "price_col":        "brent_usd_bbl",
        "unit":             "bbl",
        "notional_scale_m": 12.0,
    },
}

# Counterparty type → active commodity set
_CPTY_COMMODITIES = {
    "bank":                ["crude_oil", "lng", "natural_gas", "diesel"],
    "commodity_trader":    list(_COMMODITY_PARAMS.keys()),    # all
    "noc":                 ["crude_oil", "lng", "natural_gas"],
    "independent_producer":["crude_oil", "natural_gas"],
    "refiner":             ["crude_oil", "naphtha", "diesel"],
    "utility":             ["lng", "natural_gas", "power"],
    "petrochemical":       ["naphtha", "chemicals"],
    "shipping":            ["bunker_fuel", "crude_oil"],
    "sovereign":           ["crude_oil", "lng"],
    "corporate_buyer":     ["diesel", "natural_gas"],
}


def simulate_trading_exposure_monthly(
    counterparties: pd.DataFrame,
    macro_m: pd.DataFrame,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return trading_exposure_m."""

    # Filter to trading-book counterparties
    trading = counterparties[
        counterparties["credit_book"].isin(["trading", "both"])
    ].copy().reset_index(drop=True)

    if len(trading) == 0:
        return pd.DataFrame()

    macro = macro_m[macro_m["scenario_id"] == scenario_id].set_index("as_of_month")
    price_cols = [c["price_col"] for c in _COMMODITY_PARAMS.values()]
    price_cols_uniq = list(dict.fromkeys(price_cols))

    # Build counterparty × commodity panel (static assignments)
    cpty_comm_rows = []
    for _, cpty in trading.iterrows():
        ctype = cpty["counterparty_type"]
        comms = _CPTY_COMMODITIES.get(ctype, ["crude_oil"])
        # Sample 1-4 active commodities per counterparty
        n_comm = int(rng.integers(1, min(len(comms) + 1, 5)))
        active_comms = list(rng.choice(comms, size=n_comm, replace=False))
        for comm in active_comms:
            cpty_comm_rows.append({
                "counterparty_id":      cpty["counterparty_id"],
                "commodity":            comm,
                "wrong_way_risk":       bool(cpty["wrong_way_risk_flag"]),
                "netting":              bool(cpty["netting_agreement_flag"]),
                "csa":                  bool(cpty["csa_flag"]),
                "connected":            bool(cpty["connected_party_flag"]),
                "rev_est":              float(cpty["annual_revenue_est_usd_m"]),
                "cpty_type":            ctype,
                "country":              cpty["country"],
                "region":               cpty["region"],
            })

    if not cpty_comm_rows:
        return pd.DataFrame()

    pairs = pd.DataFrame(cpty_comm_rows)
    K = len(pairs)

    # Credit limits (counterparty × commodity, USD m)
    # Scale with counterparty revenue and commodity
    notional_scale = pairs["commodity"].map(
        {c: _COMMODITY_PARAMS[c]["notional_scale_m"] for c in _COMMODITY_PARAMS}
    ).values
    # Number of active contracts per pair (1–8)
    n_contracts = rng.integers(1, 9, K).astype(float)
    # Entry prices (set at contract inception — use first-month prices as proxy)
    first_mo = months[0]
    first_macro = macro.loc[first_mo] if first_mo in macro.index else macro.iloc[0]

    entry_prices = np.array([
        float(first_macro.get(
            _COMMODITY_PARAMS[c]["price_col"], 75.0
        )) * rng.uniform(0.90, 1.10)
        for c in pairs["commodity"]
    ])

    # Contract tenors (remaining months from start)
    max_tenors = pairs["commodity"].map(
        {c: _COMMODITY_PARAMS[c]["max_tenor_months"] for c in _COMMODITY_PARAMS}
    ).values.astype(int)
    tenors = rng.integers(1, max_tenors + 1, K).astype(float)

    # Vol multipliers by commodity
    vol_mult = pairs["commodity"].map(
        {c: _COMMODITY_PARAMS[c]["vol_annual"] for c in _COMMODITY_PARAMS}
    ).values

    # Approved trading limits (USD m) — set conservatively so ~5-10% of lines breach
    # Limit = 0.6–1.2× expected average net exposure (not full notional)
    approved_limit = notional_scale * n_contracts * rng.uniform(0.15, 0.50, K)

    slices = []

    for t, month in enumerate(months):
        mo = macro.loc[month] if month in macro.index else macro.iloc[-1]

        # Current prices for each pair's commodity
        current_prices = np.array([
            float(mo.get(_COMMODITY_PARAMS[c]["price_col"], 75.0))
            for c in pairs["commodity"]
        ])

        # Price change from entry (drives MTM)
        price_change_pct = (current_prices - entry_prices) / np.maximum(entry_prices, 1.0)

        # Notional exposure (position × notional scale × n_contracts)
        position = rng.choice([-1, 1], K, p=[0.45, 0.55])   # long/short mix
        gross_notional = notional_scale * n_contracts * current_prices / 100.0  # USD m

        # MTM
        mtm_raw = position * price_change_pct * gross_notional * rng.uniform(0.7, 1.3, K)
        mtm_positive = np.maximum(mtm_raw, 0.0)
        mtm_negative = np.maximum(-mtm_raw, 0.0)

        # Settlement exposure (undelivered contracts within settlement window)
        settle_days = pairs["commodity"].map(
            {c: _COMMODITY_PARAMS[c]["settlement_days"] for c in _COMMODITY_PARAMS}
        ).values
        settlement_exposure = gross_notional * settle_days / 30.0 * rng.uniform(0.2, 0.8, K)
        settlement_exposure = np.maximum(settlement_exposure, 0.0)

        # Replacement cost (cost to re-execute at current market)
        replacement_cost = np.abs(mtm_raw) * rng.uniform(1.1, 1.4, K)

        # Netting: reduce gross exposure
        netting_mask = pairs["netting"].values
        net_mtm_positive = np.where(netting_mask, mtm_positive * 0.35, mtm_positive)
        net_mtm_negative = np.where(netting_mask, mtm_negative * 0.35, mtm_negative)

        # CSA collateral
        csa_mask = pairs["csa"].values
        # If MTM positive → we received collateral from counterparty
        # If MTM negative → we posted collateral to counterparty
        collateral_received = np.where(csa_mask, net_mtm_positive * rng.uniform(0.80, 1.0, K), 0.0)
        collateral_posted   = np.where(csa_mask, net_mtm_negative * rng.uniform(0.80, 1.0, K), 0.0)

        # Net credit exposure = MTM_positive + settlement − collateral_received
        net_exposure = np.maximum(net_mtm_positive + settlement_exposure - collateral_received, 0.0)

        # Margin calls: triggered when net_mtm_negative exceeds threshold
        margin_threshold = approved_limit * 0.10
        margin_call = np.where(
            csa_mask & (net_mtm_negative > margin_threshold),
            net_mtm_negative - collateral_posted,
            0.0,
        )
        margin_call = np.maximum(margin_call, 0.0)

        # PFE (parametric: 95th percentile)
        remaining_months = np.maximum(tenors - t, 1)
        pfe = (net_exposure + replacement_cost) * vol_mult * np.sqrt(remaining_months / 12) * 1.65
        pfe = np.maximum(pfe, 0.0)

        # Wrong-way risk amplification
        # For oil producers: when Brent falls, their credit quality falls
        # and Shell's exposure rises (adverse correlation)
        brent = float(mo.get("brent_usd_bbl", 75.0))
        wwr_mask = pairs["wrong_way_risk"].values
        wwr_brent_factor = max(0.5, 75.0 / max(brent, 10.0))  # rises as brent falls
        net_exposure = np.where(wwr_mask, net_exposure * wwr_brent_factor, net_exposure)

        # Limit breaches
        limit_breach = net_exposure > approved_limit
        country_concentration = pairs["country"].isin(
            ["RU", "IR", "VE", "LY"]  # restricted/sanctioned countries
        ).values

        df = pd.DataFrame({
            "counterparty_id":          pairs["counterparty_id"].values,
            "commodity":                pairs["commodity"].values,
            "as_of_month":              month,
            "scenario_id":              scenario_id,
            "contract_type":            np.where(
                position > 0, "long_physical", "short_physical"
            ),
            "gross_receivable_usd_m":   np.maximum(mtm_positive + settlement_exposure, 0.0),
            "gross_payable_usd_m":      mtm_negative,
            "net_exposure_usd_m":       net_exposure,
            "mtm_positive_usd_m":       net_mtm_positive,
            "mtm_negative_usd_m":       net_mtm_negative,
            "settlement_exposure_usd_m":settlement_exposure,
            "replacement_cost_usd_m":   replacement_cost,
            "pfe_usd_m":                pfe,
            "netting_agreement_flag":   pairs["netting"].values,
            "csa_flag":                 pairs["csa"].values,
            "collateral_posted_usd_m":  collateral_posted,
            "collateral_received_usd_m":collateral_received,
            "margin_call_amount_usd_m": margin_call,
            "wrong_way_risk_flag":      wwr_mask,
            "country_concentration_flag": country_concentration,
            "limit_breach_flag":        limit_breach,
            "approved_limit_usd_m":     approved_limit,
        })
        slices.append(df)

    return pd.concat(slices, ignore_index=True)
