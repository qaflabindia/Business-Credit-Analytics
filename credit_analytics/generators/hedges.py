"""
Vectorized monthly hedge position generator.

Generates hedge programmes per borrower, then expands to monthly rows
using vectorized date arithmetic — no Python row-level loops.
"""
import numpy as np
import pandas as pd


def simulate_hedges_monthly(
    borrowers: pd.DataFrame,
    ops_m: pd.DataFrame,
    macro_m: pd.DataFrame,
    months: pd.DatetimeIndex,
    rng: np.random.Generator,
    scenario_id: str = "baseline",
) -> pd.DataFrame:
    """Return hedge_position_m rows for all borrowers."""
    macro = macro_m[macro_m["scenario_id"] == scenario_id].set_index("as_of_month")
    months_set = set(months)
    months_list = list(months)
    month_to_idx = {m: i for i, m in enumerate(months_list)}

    # Pre-fetch average production per borrower (for notional sizing)
    prod_by_brw = (
        ops_m[ops_m["scenario_id"] == scenario_id]
        .groupby("borrower_id")[["liq_prod_kboed", "gas_prod_mmscfd"]]
        .mean()
    )

    # Pre-fetch brent/gas arrays (M,) for fast MTM lookup
    brent_arr = np.array([macro["brent_usd_bbl"].get(m, 75.0) for m in months_list])
    gas_arr   = np.array([macro["henry_hub_usd_mmbtu"].get(m, 3.5) for m in months_list])

    # ── Generate hedge programme specs ────────────────────────────────────────
    prog_rows = []
    prog_counter = 0

    for _, brw in borrowers.iterrows():
        bid = brw["borrower_id"]
        hedge_ratio = float(brw["hedge_ratio"])
        if hedge_ratio < 0.01:
            continue

        n_tranches = int(rng.integers(1, 4))
        for _ in range(n_tranches):
            prog_counter += 1
            commodity = rng.choice(
                ["oil", "gas"],
                p=[0.65, 0.35] if brw["has_reserves"] else [0.50, 0.50],
            )
            instrument = rng.choice(
                ["swap", "put_option", "collar", "costless_collar"],
                p=[0.40, 0.25, 0.20, 0.15],
            )

            t0 = int(rng.integers(0, len(months_list)))
            t1 = min(t0 + int(rng.integers(6, 25)), len(months_list) - 1)

            start_m = months_list[t0]
            end_m   = months_list[t1]

            # Inception price
            inc_brent = brent_arr[t0]
            inc_gas   = gas_arr[t0]
            spot = inc_brent if commodity == "oil" else inc_gas

            fixed_price = float(spot * rng.uniform(0.90, 1.05)) if instrument == "swap" else float("nan")
            floor_price = float(spot * rng.uniform(0.75, 0.90)) if instrument in ("put_option", "collar", "costless_collar") else float("nan")
            cap_price   = float(spot * rng.uniform(1.10, 1.30)) if instrument in ("collar", "costless_collar") else float("nan")

            # Notional (boe or mmbtu pa)
            if bid in prod_by_brw.index:
                if commodity == "oil":
                    base_vol = float(prod_by_brw.loc[bid, "liq_prod_kboed"]) * 365 * 1e3
                else:
                    base_vol = float(prod_by_brw.loc[bid, "gas_prod_mmscfd"]) * 365
            else:
                base_vol = 100_000.0
            notional = max(base_vol * hedge_ratio * rng.uniform(0.6, 1.0), 0.1)

            # Partial disclosure for private/smaller names
            disclosed = not (not bool(brw["listed_flag"]) and rng.random() < 0.15)

            prog_rows.append({
                "hedge_id":         f"HDG{prog_counter:08d}",
                "borrower_id":      bid,
                "commodity":        commodity,
                "instrument_type":  instrument,
                "t0":               t0,
                "t1":               t1,
                "start_date":       start_m,
                "end_date":         end_m,
                "notional":         float(notional) if disclosed else float("nan"),
                "fixed_price":      fixed_price if disclosed else float("nan"),
                "floor_price":      floor_price if disclosed else float("nan"),
                "cap_price":        cap_price   if disclosed else float("nan"),
                "hedged_pct":       float(np.clip(hedge_ratio * rng.uniform(0.7, 1.0), 0, 0.95)),
                "listed_flag":      bool(brw["listed_flag"]),
            })

    if not prog_rows:
        return pd.DataFrame()

    progs = pd.DataFrame(prog_rows)

    # ── Expand programmes to monthly rows (vectorized) ────────────────────────
    # Build index arrays: for each programme, expand t0..t1
    prog_ids   = []
    month_idxs = []
    for pi, row in enumerate(progs.itertuples(index=False)):
        span = np.arange(row.t0, row.t1 + 1)
        prog_ids.append(np.full(len(span), pi, dtype=np.int32))
        month_idxs.append(span)

    prog_ids_arr   = np.concatenate(prog_ids)
    month_idxs_arr = np.concatenate(month_idxs)

    # Spot prices at each month
    p_commodity = progs["commodity"].values[prog_ids_arr]
    spot_arr = np.where(p_commodity == "oil", brent_arr[month_idxs_arr], gas_arr[month_idxs_arr])

    # MTM calculation
    fixed_arr = progs["fixed_price"].values[prog_ids_arr]
    floor_arr = progs["floor_price"].values[prog_ids_arr]
    cap_arr   = progs["cap_price"].values[prog_ids_arr]
    notional_arr = progs["notional"].values[prog_ids_arr]
    inst_arr  = progs["instrument_type"].values[prog_ids_arr]

    mtm = np.where(
        inst_arr == "swap",
        (fixed_arr - spot_arr) * notional_arr / 1e6,
        np.where(
            inst_arr == "put_option",
            np.maximum(floor_arr - spot_arr, 0) * notional_arr / 1e6,
            np.where(
                np.isin(inst_arr, ["collar", "costless_collar"]),
                (np.maximum(floor_arr - spot_arr, 0) - np.maximum(spot_arr - cap_arr, 0)) * notional_arr / 1e6,
                0.0,
            ),
        ),
    )
    # Zero out NaN-notional rows
    mtm = np.where(np.isnan(notional_arr), 0.0, mtm)

    out = pd.DataFrame({
        "hedge_id":                  progs["hedge_id"].values[prog_ids_arr],
        "borrower_id":               progs["borrower_id"].values[prog_ids_arr],
        "as_of_month":               np.array(months_list)[month_idxs_arr],
        "scenario_id":               scenario_id,
        "commodity":                 p_commodity,
        "instrument_type":           inst_arr,
        "start_date":                progs["start_date"].values[prog_ids_arr],
        "end_date":                  progs["end_date"].values[prog_ids_arr],
        "notional_boe_or_mmbtu":     notional_arr,
        "fixed_price":               fixed_arr,
        "floor_price":               floor_arr,
        "cap_price":                 cap_arr,
        "hedged_pct_next_12m_prod":  progs["hedged_pct"].values[prog_ids_arr],
        "mtm_usd_m":                 mtm,
    })

    return out
