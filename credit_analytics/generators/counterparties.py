"""
Customer dimension table for the O&G business AR function.

Customers are entities that buy products from the oil & gas company:
  commodity_trader   → physical crude, LNG, products, gas
  noc                → long-term supply offtake (state-owned buyers)
  independent_producer → product/gas purchases
  refiner            → crude oil, naphtha, diesel purchases
  utility            → LNG, natural gas, power
  petrochemical      → naphtha, chemicals feedstocks
  shipping           → bunker fuel
  corporate_buyer    → industrial diesel, natural gas end-users

Commodity correlated risk: a customer's creditworthiness may be correlated
with the commodity price — e.g., an oil producer buyer's revenues fall when
oil prices fall, reducing their ability to pay on time.
"""
import numpy as np
import pandas as pd

from ..config import REGIONS, REGION_WEIGHTS, RATING_GRADES, RATING_TO_PD


_CUSTOMER_SEGMENTS = {
    "commodity_trader": {
        "share": 0.15,
        "commodity_risk_prob": 0.45,
        "connected_prob": 0.08,
        "rating_mean_idx": 9,    # ~ BBB
        "rating_sigma": 4,
    },
    "noc": {
        "share": 0.10,
        "commodity_risk_prob": 0.70,
        "connected_prob": 0.15,
        "rating_mean_idx": 8,    # ~ BBB
        "rating_sigma": 5,
    },
    "independent_producer": {
        "share": 0.13,
        "commodity_risk_prob": 0.80,
        "connected_prob": 0.10,
        "rating_mean_idx": 11,   # ~ BB+
        "rating_sigma": 4,
    },
    "refiner": {
        "share": 0.12,
        "commodity_risk_prob": 0.35,
        "connected_prob": 0.06,
        "rating_mean_idx": 9,
        "rating_sigma": 4,
    },
    "utility": {
        "share": 0.15,
        "commodity_risk_prob": 0.25,
        "connected_prob": 0.05,
        "rating_mean_idx": 7,    # ~ A-
        "rating_sigma": 3,
    },
    "petrochemical": {
        "share": 0.10,
        "commodity_risk_prob": 0.30,
        "connected_prob": 0.04,
        "rating_mean_idx": 9,
        "rating_sigma": 4,
    },
    "shipping": {
        "share": 0.07,
        "commodity_risk_prob": 0.40,
        "connected_prob": 0.03,
        "rating_mean_idx": 12,   # ~ BB
        "rating_sigma": 4,
    },
    "corporate_buyer": {
        "share": 0.18,
        "commodity_risk_prob": 0.15,
        "connected_prob": 0.03,
        "rating_mean_idx": 11,
        "rating_sigma": 5,
    },
}


def generate_customers(
    n_customers: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """
    Return customer_dim — one row per customer.

    Key columns:
      customer_id, customer_type, sector, country, region,
      external_rating, commodity_risk_flag, connected_party_flag,
      kyc_status, sanctions_flag, annual_revenue_est_usd_m
    """
    seg_names = list(_CUSTOMER_SEGMENTS.keys())
    shares = np.array([_CUSTOMER_SEGMENTS[s]["share"] for s in seg_names], dtype=float)
    shares /= shares.sum()

    seg_idx = rng.choice(len(seg_names), size=n_customers, p=shares)
    segs = [seg_names[i] for i in seg_idx]

    region_names = list(REGIONS.keys())
    rows = []

    for i, seg in enumerate(segs):
        sp = _CUSTOMER_SEGMENTS[seg]

        region = rng.choice(region_names, p=REGION_WEIGHTS)
        country = rng.choice(REGIONS[region])

        raw_idx = int(np.clip(
            rng.normal(sp["rating_mean_idx"], sp["rating_sigma"]),
            0, len(RATING_GRADES) - 1,
        ))
        ext_rating = RATING_GRADES[raw_idx]

        kyc_draw = rng.random()
        kyc_status = (
            "approved" if kyc_draw > 0.05
            else ("pending" if kyc_draw > 0.02 else "flagged")
        )
        sanctions = (rng.random() < 0.005) and (kyc_status == "flagged")

        rows.append({
            "customer_id":               f"CST{i + 1:06d}",
            "customer_type":              seg,
            "sector":                     _sector(seg),
            "country":                    country,
            "region":                     region,
            "external_rating":            ext_rating,
            "commodity_risk_flag":        rng.random() < sp["commodity_risk_prob"],
            "connected_party_flag":       rng.random() < sp["connected_prob"],
            "kyc_status":                 kyc_status,
            "sanctions_flag":             bool(sanctions),
            "annual_revenue_est_usd_m":   float(np.exp(rng.normal(np.log(500), 1.5))),
        })

    return pd.DataFrame(rows)


def _sector(ctype: str) -> str:
    return {
        "commodity_trader":    "energy_trading",
        "noc":                 "integrated_energy",
        "independent_producer":"upstream_oil_gas",
        "refiner":             "refining_marketing",
        "utility":             "utilities",
        "petrochemical":       "chemicals",
        "shipping":            "marine_transport",
        "corporate_buyer":     "industrial",
    }.get(ctype, "other")
