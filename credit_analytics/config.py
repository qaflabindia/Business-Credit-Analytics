"""Configuration and reference data for the O&G business AR analytics generator."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List

MASTER_SEED = 20260605

SEEDS: Dict[str, int] = {
    "calendar":     20260606,
    "macro":        20260607,
    "customers":    20260608,
    "trade_credit": 20260609,
    "dq_noise":     20260619,
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

# Rating grades (D treated as defaulted — not assigned here)
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

# Macro baseline (monthly levels) — commodity prices + economic indicators
MACRO_BASELINE: Dict[str, float] = {
    "global_gdp_yoy":         3.0,
    "us_gdp_yoy":             2.5,
    "eu_gdp_yoy":             1.5,
    "uk_gdp_yoy":             1.5,
    "unemployment_us":        4.0,
    "bbb_spread_bps":       150.0,   # credit market stress proxy
    "brent_usd_bbl":         75.0,
    "henry_hub_usd_mmbtu":    3.5,
    "ttf_usd_mmbtu":         10.0,
    "jkm_usd_mmbtu":         12.0,
    "carbon_price_usd_tco2": 50.0,
    "usd_index":            103.0,
    "shipping_cost_index":  100.0,
}


@dataclass
class Config:
    n_customers: int = 2_000
    n_months: int = 120
    start_date: str = "2016-01-31"
    master_seed: int = MASTER_SEED
    output_dir: str = "data_out"
    scale: str = "standard"
    generate_scenarios: List[str] = field(
        default_factory=lambda: [
            "baseline", "severe_demand",
            "geopolitical_supply", "disorderly_transition",
        ]
    )

    @classmethod
    def lite(cls) -> "Config":
        return cls(n_customers=500, n_months=36, scale="lite",
                   generate_scenarios=["baseline", "severe_demand"])

    @classmethod
    def standard(cls) -> "Config":
        return cls(n_customers=2_000, n_months=120, scale="standard")

    @classmethod
    def research(cls) -> "Config":
        return cls(n_customers=8_000, n_months=180, scale="research")

    def rng(self, key: str) -> "np.random.Generator":
        import numpy as np
        return np.random.default_rng(SEEDS[key])
