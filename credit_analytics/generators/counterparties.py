"""
Counterparty dimension table.

Counterparties are distinct from borrowers:
  - A borrower has a credit facility with Shell.
  - A counterparty is any entity Shell trades with, settles against,
    or holds receivables from.
  - Some counterparties are also borrowers; most are not.

Counterparty types and their credit book:
  bank               → trading book (derivatives, settlements, FX)
  commodity_trader   → trading book (crude, LNG, products, gas)
  noc                → both books (long-term supply, trading)
  independent_producer → both books (sales, sometimes RBL counterparty)
  refiner            → trade book (product purchases from Shell)
  utility            → trade book (LNG, gas, power)
  petrochemical      → trade book (feedstocks, chemicals)
  shipping           → trade book (freight, voyage charters)
  sovereign          → trading book (EM sovereign risk)
  corporate_buyer    → trade book only (industrial customers)

Wrong-way risk (WWR): counterparty credit quality is inversely correlated
with Shell's exposure — e.g., an oil producer's creditworthiness falls
exactly when oil prices fall, and Shell's own earnings are also stressed.
"""
import numpy as np
import pandas as pd
from typing import List

from ..config import REGIONS, REGION_WEIGHTS, RATING_GRADES, RATING_TO_PD


_CPTY_SEGMENTS = {
    "bank": {
        "share": 0.14,
        "books": ["trading"],
        "wwr_prob": 0.10,    # low: banks diversified
        "connected_prob": 0.05,
        "rating_mean_idx": 5,   # ~ A
        "rating_sigma": 3,
        "netting_prob": 0.90,
        "csa_prob": 0.80,
    },
    "commodity_trader": {
        "share": 0.12,
        "books": ["trading"],
        "wwr_prob": 0.45,    # medium: correlated with commodity cycle
        "connected_prob": 0.08,
        "rating_mean_idx": 9,   # ~ BBB
        "rating_sigma": 4,
        "netting_prob": 0.70,
        "csa_prob": 0.50,
    },
    "noc": {
        "share": 0.08,
        "books": ["trading", "trade"],
        "wwr_prob": 0.70,    # high: state-owned, commodity-linked, political risk
        "connected_prob": 0.15,
        "rating_mean_idx": 8,   # ~ BBB
        "rating_sigma": 5,
        "netting_prob": 0.40,
        "csa_prob": 0.20,
    },
    "independent_producer": {
        "share": 0.10,
        "books": ["trading", "trade"],
        "wwr_prob": 0.80,    # very high: same commodity exposure as Shell
        "connected_prob": 0.10,
        "rating_mean_idx": 11,  # ~ BB+
        "rating_sigma": 4,
        "netting_prob": 0.30,
        "csa_prob": 0.15,
    },
    "refiner": {
        "share": 0.10,
        "books": ["trade"],
        "wwr_prob": 0.35,
        "connected_prob": 0.06,
        "rating_mean_idx": 9,
        "rating_sigma": 4,
        "netting_prob": 0.20,
        "csa_prob": 0.10,
    },
    "utility": {
        "share": 0.12,
        "books": ["trade"],
        "wwr_prob": 0.25,
        "connected_prob": 0.05,
        "rating_mean_idx": 7,   # ~ A-
        "rating_sigma": 3,
        "netting_prob": 0.25,
        "csa_prob": 0.15,
    },
    "petrochemical": {
        "share": 0.08,
        "books": ["trade"],
        "wwr_prob": 0.30,
        "connected_prob": 0.04,
        "rating_mean_idx": 9,
        "rating_sigma": 4,
        "netting_prob": 0.15,
        "csa_prob": 0.08,
    },
    "shipping": {
        "share": 0.06,
        "books": ["trade"],
        "wwr_prob": 0.40,    # oil-price correlated
        "connected_prob": 0.03,
        "rating_mean_idx": 12, # ~ BB
        "rating_sigma": 4,
        "netting_prob": 0.10,
        "csa_prob": 0.05,
    },
    "sovereign": {
        "share": 0.06,
        "books": ["trading"],
        "wwr_prob": 0.60,    # high: oil-exporting sovereigns
        "connected_prob": 0.20,
        "rating_mean_idx": 10, # ~ BBB-
        "rating_sigma": 5,
        "netting_prob": 0.20,
        "csa_prob": 0.05,
    },
    "corporate_buyer": {
        "share": 0.14,
        "books": ["trade"],
        "wwr_prob": 0.15,
        "connected_prob": 0.03,
        "rating_mean_idx": 11,
        "rating_sigma": 5,
        "netting_prob": 0.05,
        "csa_prob": 0.03,
    },
}


def generate_counterparties(
    n_counterparties: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Return counterparty_dim — one row per counterparty.

    Key columns:
      counterparty_id, counterparty_type, sector, country, region,
      external_rating, wrong_way_risk_flag, connected_party_flag,
      netting_agreement_flag, csa_flag, kyc_status, sanctions_flag,
      credit_book (trading | trade | both)
    """
    seg_names = list(_CPTY_SEGMENTS.keys())
    shares = np.array([_CPTY_SEGMENTS[s]["share"] for s in seg_names], dtype=float)
    shares /= shares.sum()

    seg_idx = rng.choice(len(seg_names), size=n_counterparties, p=shares)
    segs = [seg_names[i] for i in seg_idx]

    region_names = list(REGIONS.keys())
    rows = []

    for i, seg in enumerate(segs):
        sp = _CPTY_SEGMENTS[seg]

        region = rng.choice(region_names, p=REGION_WEIGHTS)
        country = rng.choice(REGIONS[region])

        # External rating (truncated normal around segment mean)
        raw_idx = int(np.clip(
            rng.normal(sp["rating_mean_idx"], sp["rating_sigma"]),
            0, len(RATING_GRADES) - 1,
        ))
        ext_rating = RATING_GRADES[raw_idx]

        books = sp["books"]
        credit_book = "both" if len(books) == 2 else books[0]

        # KYC status (most are approved; ~3% pending or flagged)
        kyc_draw = rng.random()
        kyc_status = "approved" if kyc_draw > 0.05 else ("pending" if kyc_draw > 0.02 else "flagged")

        # Sanctions: very rare but included for realism
        sanctions = (rng.random() < 0.005) and (kyc_status == "flagged")

        rows.append({
            "counterparty_id":        f"CPT{i + 1:06d}",
            "counterparty_type":       seg,
            "sector":                  _sector(seg),
            "country":                 country,
            "region":                  region,
            "external_rating":         ext_rating,
            "wrong_way_risk_flag":     rng.random() < sp["wwr_prob"],
            "connected_party_flag":    rng.random() < sp["connected_prob"],
            "netting_agreement_flag":  rng.random() < sp["netting_prob"],
            "csa_flag":                rng.random() < sp["csa_prob"],
            "kyc_status":              kyc_status,
            "sanctions_flag":          bool(sanctions),
            "credit_book":             credit_book,
            "annual_revenue_est_usd_m": float(np.exp(
                rng.normal(np.log(500), 1.5)
            )),
        })

    return pd.DataFrame(rows)


def _sector(ctype: str) -> str:
    mapping = {
        "bank":                "financials",
        "commodity_trader":    "energy_trading",
        "noc":                 "integrated_energy",
        "independent_producer":"upstream_oil_gas",
        "refiner":             "refining_marketing",
        "utility":             "utilities",
        "petrochemical":       "chemicals",
        "shipping":            "marine_transport",
        "sovereign":           "government",
        "corporate_buyer":     "industrial",
    }
    return mapping.get(ctype, "other")
