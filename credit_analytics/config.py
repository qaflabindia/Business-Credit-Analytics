"""Configuration, segment parameters, and rating mappings."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional

MASTER_SEED = 20260605

SEEDS: Dict[str, int] = {
    "calendar":    20260606,
    "macro":       20260607,
    "borrowers":   20260608,
    "facilities":  20260609,
    "financials":  20260610,
    "operations":  20260611,
    "reserves":    20260612,
    "hedges":      20260613,
    "snapshots":   20260614,
    "covenants":   20260615,
    "ratings":     20260616,
    "defaults":    20260617,
    "recoveries":  20260618,
    "dq_noise":    20260619,
}

# Segment calibration anchored to Shell-like integrated supermajor archetypes
SEGMENTS: Dict[str, dict] = {
    "supermajor": {
        "share": 0.005,
        "revenue_median_usd_m": 300_000,
        "revenue_log_sigma": 0.30,
        "leverage_median": 1.2,
        "leverage_sigma": 0.25,
        "reserve_life_median": 8.5,
        "reserve_life_sigma": 1.0,
        "hedge_ratio_median": 0.12,
        "hedge_ratio_sigma": 0.04,
        "ebitda_margin_mean": 0.25,
        "ebitda_margin_sigma": 0.03,
        "mu_revenue": 0.010,       # quarterly log-revenue drift
        "beta_oil": 0.40,
        "beta_gas": 0.15,
        "beta_gdp": 0.05,
        "alpha_pd": -5.80,         # logit intercept → very low PD
        "beta_commodity": 0.30,
        "has_reserves": True,
        "offshore_share_mean": 0.40,
        "offshore_share_sigma": 0.10,
        "facilities_per_borrower": (3, 6),
        "facility_types": ["RCF", "term_loan", "bond", "trade_finance"],
        "listed_share": 1.00,
        "ownership_types": ["public"],
    },
    "large_integrated": {
        "share": 0.035,
        "revenue_median_usd_m": 55_000,
        "revenue_log_sigma": 0.40,
        "leverage_median": 1.8,
        "leverage_sigma": 0.40,
        "reserve_life_median": 9.0,
        "reserve_life_sigma": 1.5,
        "hedge_ratio_median": 0.15,
        "hedge_ratio_sigma": 0.06,
        "ebitda_margin_mean": 0.22,
        "ebitda_margin_sigma": 0.04,
        "mu_revenue": 0.008,
        "beta_oil": 0.45,
        "beta_gas": 0.18,
        "beta_gdp": 0.06,
        "alpha_pd": -4.60,
        "beta_commodity": 0.40,
        "has_reserves": True,
        "offshore_share_mean": 0.35,
        "offshore_share_sigma": 0.10,
        "facilities_per_borrower": (2, 5),
        "facility_types": ["RCF", "term_loan", "bond", "trade_finance"],
        "listed_share": 0.90,
        "ownership_types": ["public", "soe"],
    },
    "independent_upstream": {
        "share": 0.32,
        "revenue_median_usd_m": 4_000,
        "revenue_log_sigma": 0.60,
        "leverage_median": 2.8,
        "leverage_sigma": 0.70,
        "reserve_life_median": 7.0,
        "reserve_life_sigma": 2.0,
        "hedge_ratio_median": 0.48,
        "hedge_ratio_sigma": 0.14,
        "ebitda_margin_mean": 0.45,
        "ebitda_margin_sigma": 0.09,
        "mu_revenue": 0.005,
        "beta_oil": 0.70,
        "beta_gas": 0.30,
        "beta_gdp": 0.03,
        "alpha_pd": -3.20,
        "beta_commodity": 0.70,
        "has_reserves": True,
        "offshore_share_mean": 0.20,
        "offshore_share_sigma": 0.12,
        "facilities_per_borrower": (2, 4),
        "facility_types": ["RBL", "RCF", "term_loan"],
        "listed_share": 0.55,
        "ownership_types": ["public", "private"],
    },
    "midstream_lng": {
        "share": 0.12,
        "revenue_median_usd_m": 5_500,
        "revenue_log_sigma": 0.45,
        "leverage_median": 3.6,
        "leverage_sigma": 0.60,
        "reserve_life_median": 10.0,
        "reserve_life_sigma": 2.0,
        "hedge_ratio_median": 0.25,
        "hedge_ratio_sigma": 0.09,
        "ebitda_margin_mean": 0.35,
        "ebitda_margin_sigma": 0.06,
        "mu_revenue": 0.006,
        "beta_oil": 0.20,
        "beta_gas": 0.50,
        "beta_gdp": 0.08,
        "alpha_pd": -3.80,
        "beta_commodity": 0.35,
        "has_reserves": False,
        "offshore_share_mean": 0.10,
        "offshore_share_sigma": 0.07,
        "facilities_per_borrower": (2, 4),
        "facility_types": ["RCF", "term_loan", "bond"],
        "listed_share": 0.60,
        "ownership_types": ["public", "private", "soe"],
    },
    "refining_marketing": {
        "share": 0.10,
        "revenue_median_usd_m": 8_500,
        "revenue_log_sigma": 0.45,
        "leverage_median": 2.1,
        "leverage_sigma": 0.50,
        "reserve_life_median": None,
        "reserve_life_sigma": 0.0,
        "hedge_ratio_median": 0.20,
        "hedge_ratio_sigma": 0.08,
        "ebitda_margin_mean": 0.08,
        "ebitda_margin_sigma": 0.025,
        "mu_revenue": 0.004,
        "beta_oil": -0.30,         # crack-spread driven; negative to crude
        "beta_gas": 0.10,
        "beta_gdp": 0.15,
        "alpha_pd": -4.00,
        "beta_commodity": 0.20,
        "has_reserves": False,
        "offshore_share_mean": 0.0,
        "offshore_share_sigma": 0.0,
        "facilities_per_borrower": (2, 4),
        "facility_types": ["RCF", "term_loan", "trade_finance"],
        "listed_share": 0.50,
        "ownership_types": ["public", "private"],
    },
    "oilfield_services": {
        "share": 0.23,
        "revenue_median_usd_m": 1_800,
        "revenue_log_sigma": 0.65,
        "leverage_median": 2.5,
        "leverage_sigma": 0.80,
        "reserve_life_median": None,
        "reserve_life_sigma": 0.0,
        "hedge_ratio_median": 0.05,
        "hedge_ratio_sigma": 0.03,
        "ebitda_margin_mean": 0.15,
        "ebitda_margin_sigma": 0.05,
        "mu_revenue": 0.003,
        "beta_oil": 0.35,
        "beta_gas": 0.15,
        "beta_gdp": 0.12,
        "alpha_pd": -3.50,
        "beta_commodity": 0.30,
        "has_reserves": False,
        "offshore_share_mean": 0.0,
        "offshore_share_sigma": 0.0,
        "facilities_per_borrower": (1, 3),
        "facility_types": ["RCF", "term_loan"],
        "listed_share": 0.40,
        "ownership_types": ["public", "private"],
    },
    "trading_petrochemicals": {
        "share": 0.19,
        "revenue_median_usd_m": 3_200,
        "revenue_log_sigma": 0.55,
        "leverage_median": 2.0,
        "leverage_sigma": 0.50,
        "reserve_life_median": None,
        "reserve_life_sigma": 0.0,
        "hedge_ratio_median": 0.18,
        "hedge_ratio_sigma": 0.08,
        "ebitda_margin_mean": 0.06,
        "ebitda_margin_sigma": 0.020,
        "mu_revenue": 0.005,
        "beta_oil": 0.25,
        "beta_gas": 0.20,
        "beta_gdp": 0.18,
        "alpha_pd": -4.20,
        "beta_commodity": 0.25,
        "has_reserves": False,
        "offshore_share_mean": 0.0,
        "offshore_share_sigma": 0.0,
        "facilities_per_borrower": (1, 3),
        "facility_types": ["RCF", "trade_finance"],
        "listed_share": 0.45,
        "ownership_types": ["public", "private"],
    },
}

REGIONS: Dict[str, List[str]] = {
    "North_America":    ["US", "CA", "MX"],
    "Europe":           ["GB", "NO", "NL", "FR", "DE", "IT"],
    "Middle_East":      ["SA", "AE", "KW", "QA", "OM"],
    "Asia_Pacific":     ["AU", "MY", "SG", "JP", "CN"],
    "Latin_America":    ["BR", "CO", "AR", "PE"],
    "Africa":           ["NG", "AO", "EG", "LY", "GH"],
}

REGION_WEIGHTS = [0.30, 0.25, 0.18, 0.12, 0.10, 0.05]

# Rating grades (exclude D — treated as defaulted state)
RATING_GRADES: List[str] = [
    "AAA", "AA+", "AA", "AA-",
    "A+",  "A",   "A-",
    "BBB+","BBB", "BBB-",
    "BB+", "BB",  "BB-",
    "B+",  "B",   "B-",
    "CCC+","CCC", "CCC-",
    "CC",  "C",
]

# Long-run average 1-year PD by rating (agency-calibrated approximation)
RATING_TO_PD: Dict[str, float] = {
    "AAA": 0.0002, "AA+": 0.0004, "AA": 0.0006, "AA-": 0.0009,
    "A+":  0.0013, "A":   0.0018, "A-": 0.0025,
    "BBB+":0.0040, "BBB": 0.0060, "BBB-":0.0090,
    "BB+": 0.0140, "BB":  0.0210, "BB-": 0.0310,
    "B+":  0.0450, "B":   0.0650, "B-":  0.0950,
    "CCC+":0.1400, "CCC": 0.2000, "CCC-":0.2600,
    "CC":  0.3500, "C":   0.4500,
}

RATING_TO_INDEX: Dict[str, int] = {r: i for i, r in enumerate(RATING_GRADES)}

# Seniority ordering for recovery
SENIORITY_LEVELS = ["senior_secured", "senior_unsecured", "subordinated"]
SENIORITY_RR_MEAN: Dict[str, float] = {
    "senior_secured":   0.65,
    "senior_unsecured": 0.45,
    "subordinated":     0.22,
}
SENIORITY_RR_SIGMA: Dict[str, float] = {
    "senior_secured":   0.20,
    "senior_unsecured": 0.22,
    "subordinated":     0.18,
}

# Macro baseline (monthly levels)
MACRO_BASELINE: Dict[str, float] = {
    "global_gdp_yoy":         3.0,
    "us_gdp_yoy":             2.5,
    "eu_gdp_yoy":             1.5,
    "uk_gdp_yoy":             1.5,
    "unemployment_us":        4.0,
    "bbb_spread_bps":       150.0,
    "policy_rate_bps":      450.0,
    "brent_usd_bbl":         75.0,
    "henry_hub_usd_mmbtu":    3.5,
    "ttf_usd_mmbtu":         10.0,
    "jkm_usd_mmbtu":         12.0,
    "carbon_price_usd_tco2": 50.0,
    "usd_index":            103.0,
    "shipping_cost_index":  100.0,
}

SCENARIOS: List[str] = [
    "baseline",
    "severe_demand",
    "geopolitical_supply",
    "disorderly_transition",
]


@dataclass
class Config:
    n_borrowers: int = 4_000
    n_months: int = 120
    start_date: str = "2016-01-31"
    master_seed: int = MASTER_SEED
    output_dir: str = "data_out"
    scale: str = "standard"
    generate_scenarios: List[str] = field(
        default_factory=lambda: ["baseline", "severe_demand", "geopolitical_supply", "disorderly_transition"]
    )

    @classmethod
    def lite(cls) -> "Config":
        return cls(n_borrowers=1_000, n_months=36, scale="lite",
                   generate_scenarios=["baseline", "severe_demand"])

    @classmethod
    def standard(cls) -> "Config":
        return cls(n_borrowers=4_000, n_months=120, scale="standard")

    @classmethod
    def research(cls) -> "Config":
        return cls(n_borrowers=15_000, n_months=180, scale="research")

    @property
    def n_quarters(self) -> int:
        return self.n_months // 3

    def rng(self, key: str) -> "np.random.Generator":
        import numpy as np
        return np.random.default_rng(SEEDS[key])
