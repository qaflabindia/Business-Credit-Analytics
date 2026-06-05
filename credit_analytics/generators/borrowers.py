"""Borrower dimension table generator."""
import numpy as np
import pandas as pd
from typing import List

from ..config import SEGMENTS, REGIONS, REGION_WEIGHTS


def generate_borrowers(n_borrowers: int, rng: np.random.Generator) -> pd.DataFrame:
    """
    Return borrower_dim with one row per borrower.

    Key columns:
      borrower_id, segment, country, region, ownership_type, listed_flag,
      fiscal_year_end_month, shell_like_flag, has_reserves,
      revenue_init_usd_m, ebitda_margin_init, leverage_init,
      hedge_ratio, beta_oil, beta_gas, beta_gdp, beta_commodity, alpha_pd,
      mu_revenue, offshore_share, mature_asset_share,
      decomm_prov_undisc_init_usd_m, reserve_life_init
    """
    segment_names: List[str] = list(SEGMENTS.keys())
    shares = np.array([SEGMENTS[s]["share"] for s in segment_names], dtype=float)
    shares /= shares.sum()

    seg_idx = rng.choice(len(segment_names), size=n_borrowers, p=shares)
    segments_assigned = [segment_names[i] for i in seg_idx]

    region_names = list(REGIONS.keys())

    rows = []
    for i in range(n_borrowers):
        seg = segments_assigned[i]
        sp = SEGMENTS[seg]

        # Geography
        region = rng.choice(region_names, p=REGION_WEIGHTS)
        country = rng.choice(REGIONS[region])

        # Ownership
        own_types = sp["ownership_types"]
        ownership = rng.choice(own_types)
        listed = (rng.random() < sp["listed_share"]) and (ownership != "private")

        # Revenue (log-normal around median)
        log_rev = np.log(sp["revenue_median_usd_m"]) + sp["revenue_log_sigma"] * rng.normal()
        revenue = float(np.exp(log_rev))

        # Leverage (truncated normal)
        leverage = float(max(0.20, sp["leverage_median"] + sp["leverage_sigma"] * rng.normal()))

        # EBITDA margin
        margin = float(np.clip(
            sp["ebitda_margin_mean"] + sp["ebitda_margin_sigma"] * rng.normal(),
            0.01, 0.85,
        ))

        # Reserve life (upstream only)
        has_res = sp["has_reserves"]
        rl_med = sp["reserve_life_median"]
        if has_res and rl_med is not None:
            reserve_life = float(max(0.5, rl_med + sp["reserve_life_sigma"] * rng.normal()))
        else:
            reserve_life = float("nan")

        # Hedge ratio (beta-like, clipped)
        hedge = float(np.clip(
            sp["hedge_ratio_median"] + sp["hedge_ratio_sigma"] * rng.normal(),
            0.0, 0.95,
        ))

        # Offshore share
        if sp["offshore_share_mean"] > 0:
            offshore = float(np.clip(
                sp["offshore_share_mean"] + sp["offshore_share_sigma"] * rng.normal(),
                0.0, 1.0,
            ))
        else:
            offshore = 0.0

        # Mature asset share
        mature = float(np.clip(rng.beta(2, 3), 0.0, 1.0)) if has_res else 0.0

        # Decommissioning provision (undiscounted)
        if has_res:
            decomm_undisc = float(revenue * margin * offshore * mature * rng.uniform(0.3, 1.8))
        else:
            decomm_undisc = 0.0

        # Idiosyncratic commodity beta (scatter around segment mean)
        beta_commodity = float(sp["beta_commodity"] * rng.uniform(0.7, 1.3))

        rows.append({
            "borrower_id":               f"BRW{i + 1:06d}",
            "segment":                    seg,
            "country":                    country,
            "region":                     region,
            "ownership_type":             ownership,
            "listed_flag":                listed,
            "fiscal_year_end_month":      int(rng.choice([3, 6, 9, 12])),
            "shell_like_flag":            seg in ("supermajor", "large_integrated"),
            "has_reserves":               has_res,
            "revenue_init_usd_m":         revenue,
            "ebitda_margin_init":         margin,
            "leverage_init":              leverage,
            "hedge_ratio":                hedge,
            "offshore_share":             offshore,
            "mature_asset_share":         mature,
            "decomm_prov_undisc_init_usd_m": decomm_undisc,
            "reserve_life_init":          reserve_life,
            "beta_oil":                   sp["beta_oil"],
            "beta_gas":                   sp["beta_gas"],
            "beta_gdp":                   sp["beta_gdp"],
            "beta_commodity":             beta_commodity,
            "alpha_pd":                   sp["alpha_pd"],
            "mu_revenue":                 sp["mu_revenue"],
        })

    return pd.DataFrame(rows)
