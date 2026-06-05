# Synthetic O&G Business AR Credit Dataset Design

## Executive summary

This document describes the design of a synthetic dataset for an **Oil & Gas company's commercial credit / accounts-receivable (AR) function** — the team that manages credit limits, AR ageing, credit holds, and collections for customers who buy petroleum products, LNG, chemicals, and other goods on credit.

The design target is the **commercial credit function of a Shell-like integrated energy company**. Shell's commercial credit team manages trade receivables from thousands of customers across eight buyer types: commodity traders, national oil companies (NOCs), independent producers, refiners, utilities, petrochemical companies, shipping companies, and industrial corporate buyers. The dataset is calibrated to the scale, credit quality distribution, and payment behaviour that is realistic for this function.

The recommended baseline configuration is **2,000 customers**, **120 monthly periods**, and **four macro scenarios**. The output is three parquet tables: a customer master, a macro/commodity path table, and a monthly AR ageing table.

---

## Calibration anchors and use cases

Shell's commercial credit function manages trade receivables from a wide range of counterparties. Key features that shape the dataset design:

- **Credit tiering** — customers are grouped by external rating into four credit tiers (investment grade strong, investment grade, sub-investment grade, high risk), with different approved limits, payment terms, and overdue behaviour per tier
- **Commodity-correlated risk** — some customers (upstream producers, NOCs, commodity traders) have payment behaviour that is correlated with oil and gas prices: when prices fall, their revenues fall and their overdue rates rise
- **Risk mitigants** — letters of credit, guarantees, credit insurance, and collateral are more common for lower-quality customers
- **Macro stress transmission** — economic downturns and credit spread widening raise overdue rates across all tiers; commodity price falls add further stress for commodity-correlated customers

The dataset supports four primary use cases:

| Use case | What the dataset enables |
|---|---|
| AR monitoring and ageing analysis | Track overdue buckets, identify deteriorating customers, measure collection efficiency |
| Credit limit management | Validate limit-setting models against known ground truth; optimise limits by segment |
| Collections and credit-hold analytics | Build and test credit-hold trigger models; measure effectiveness of risk mitigants |
| Stress testing | Quantify AR at risk and expected bad debt under four macro scenarios |

---

## Schema and design choices

The dataset uses a simple three-table structure.

### Customer master

| Table | Grain | Key fields |
|---|---|---|
| `customer_dim` | One row per customer | `customer_id`, `customer_type`, `sector`, `country`, `region`, `external_rating`, `commodity_risk_flag`, `connected_party_flag`, `kyc_status`, `sanctions_flag`, `annual_revenue_est_usd_m` |

### Macro environment

| Table | Grain | Key fields |
|---|---|---|
| `macro_scenario_m` | One row per month per scenario | `scenario_id`, `as_of_month`, `brent_usd_bbl`, `henry_hub_usd_mmbtu`, `ttf_usd_mmbtu`, `jkm_usd_mmbtu`, `global_gdp_yoy`, `us_gdp_yoy`, `bbb_spread_bps`, `carbon_price_usd_tco2`, `usd_index`, `shipping_cost_index` |

### AR ageing and credit terms

| Table | Grain | Key fields |
|---|---|---|
| `trade_credit_terms_m` | One row per customer per month per scenario | `customer_id`, `as_of_month`, `scenario_id`, `payment_terms_days`, `approved_credit_limit_usd_m`, `temporary_credit_limit_usd_m`, `current_ar_usd_m`, `ar_not_due_usd_m`, `ar_1_30_dpd_usd_m`, `ar_31_60_dpd_usd_m`, `ar_61_90_dpd_usd_m`, `ar_90_plus_dpd_usd_m`, `utilisation_pct`, `blocked_order_flag`, `credit_hold_flag`, `letter_of_credit_flag`, `guarantee_flag`, `credit_insurance_flag`, `collateral_required_flag`, `collateral_value_usd_m` |

---

## Customer segments

Eight customer types are modelled, representing the full range of O&G commercial buyers:

| Customer type | Portfolio share | Rating anchor | Commodity risk | Typical payment terms |
|---|---:|---|---|---|
| `commodity_trader` | 15% | BBB | Medium (45%) | 30–60 days |
| `corporate_buyer` | 18% | BB+ | Low (15%) | 7–45 days |
| `utility` | 15% | A- | Low (25%) | 30–45 days |
| `noc` | 10% | BBB | High (70%) | 30–60 days |
| `independent_producer` | 13% | BB+ | Very high (80%) | 14–30 days |
| `refiner` | 12% | BBB | Medium (35%) | 30–60 days |
| `petrochemical` | 10% | BBB | Medium (30%) | 30–60 days |
| `shipping` | 7% | BB | Medium-high (40%) | 7–30 days |

---

## Credit tier calibration

Customers are mapped to one of four credit tiers based on external rating:

| Tier | Rating range | Payment terms | Approved limit range | Overdue probability | Hold threshold |
|---|---|---|---|---|---|
| Tier 1 | AAA–A- | 30–45 days | USD 5–50m | 3% | 25% overdue/limit |
| Tier 2 | BBB+–BBB- | 30–60 days | USD 2–20m | 8% | 20% overdue/limit |
| Tier 3 | BB+–BB- | 14–30 days | USD 0.5–8m | 16% | 18% overdue/limit |
| Tier 4 | B and below | 7–14 days | USD 0.1–3m | 28% | 15% overdue/limit |

---

## AR ageing model

AR is generated as a causal bucket model. Each month:

1. **New deliveries** are generated as a fraction of the approved credit limit, tier-calibrated
2. **New overdue inductions** — a fraction of new AR slips immediately to the 1–30 DPD bucket, driven by the customer's base overdue probability × macro stress multiplier
3. **Bucket aging** — unpaid AR ages from 1–30 → 31–60 → 61–90 → 90+ DPD each month, with tier-calibrated collection probabilities at each stage
4. **Credit holds** — triggered when total overdue / approved limit exceeds the tier threshold; cured when it falls below half the threshold
5. **Blocked orders** — triggered when the 90+ DPD bucket exceeds 10% of approved limit

### Macro stress transmission

The overdue induction rate is multiplied by a macro stress factor:

```
macro_mult = 1.0
           + 1.5 × max(0, (3.0 − GDP_yoy) / 3.0)     ← GDP stress
           + 1.0 × max(0, (BBBspread − 150) / 300)    ← credit market stress

For commodity-risk customers, an additional oil-price stress applies:
           + 1.0 × max(0, (75 − Brent) / 75)          ← commodity stress
```

---

## Scenario set

| Scenario | Calibration | Key overlays |
|---|---|---|
| `baseline` | IMF 2026 and EIA 2026 path | Brent ~$75, GDP ~3%, BBB spreads ~150 bps |
| `severe_demand` | Fed 2026 severely adverse | GDP −4.6%, Brent −35%, spreads +250 bps (months 30–60) |
| `geopolitical_supply` | Middle East supply disruption | Brent +50%, TTF +70%, shipping +80% (months 45–72) |
| `disorderly_transition` | Abrupt energy transition | Brent −20%, carbon ×2.5 (months 60–end) |

---

## Data quality injection

The dataset includes controlled AR imperfections for realism:

| Issue | Rate | Pattern |
|---|---|---|
| Late credit review date (NaN) | ~4% of small customers | Small customers by revenue |
| AR bucket rounding artefacts | ~8% of rows | Manual-entry simulation |
| Missing temporary limit records | ~3% of rows | System upload gaps |
| Duplicate month-end snapshots | ~0.03% of rows | Double-posting artefact |

---

## Validation checks

Every generated dataset is validated against eight realism checks:

| Check | Pass condition |
|---|---|
| Bucket consistency | Sum of AR buckets = total AR (< 1% error) |
| Credit limits positive | No non-positive approved limits |
| Credit limits bounded | No approved limit > USD 1 000m |
| Utilisation distribution | < 20% of rows have zero AR |
| Utilisation cap | < 5% of rows exceed 150% utilisation |
| Hold/overdue correlation | Credit-hold customers have higher overdue rate than non-hold customers |
| Commodity risk customers | Commodity-risk customers have higher overdue rate in baseline |
| Payment terms range | All payment terms in [7, 90] days |

---

## Python implementation

```python
MASTER_SEED = 20260605
SEEDS = {
    "calendar":     20260606,
    "macro":        20260607,
    "customers":    20260608,
    "trade_credit": 20260609,
    "dq_noise":     20260619,
}
```

### Pipeline flow

```
calendar → macro paths → customer master
  → for each scenario:
      simulate_trade_credit_monthly()
      append to trade_credit_terms_m.parquet
  → inject noise (baseline slice)
  → validate
  → write static tables
```

### Example analyses

```python
import pandas as pd

# AR overdue rate by scenario
ar = pd.read_parquet("data_out/trade_credit_terms_m.parquet")
ar["overdue_rate"] = (
    ar["ar_1_30_dpd_usd_m"] + ar["ar_31_60_dpd_usd_m"]
    + ar["ar_61_90_dpd_usd_m"] + ar["ar_90_plus_dpd_usd_m"]
) / ar["current_ar_usd_m"].clip(lower=0.001)

summary = ar.groupby(["scenario_id", "as_of_month"])["overdue_rate"].mean()
print(summary.unstack("scenario_id").tail(6).round(3))
```

---

## Open questions and limitations

Some parameter values are **design choices**, not empirically observed market rates. They represent a realistic starting point calibrated to the commercial credit function of a large integrated energy company, and should be tuned to the institution's actual customer mix, product lines, geography, and observed payment behaviour.

The dataset does not model individual invoice-level AR — it operates at the customer-month level with bucket aggregates. An invoice-level extension is feasible but increases complexity substantially and is not needed for the primary use cases.
