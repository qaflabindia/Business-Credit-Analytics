# Credit Analytics — Data Dictionary

**Dataset:** Synthetic O&G Business AR Credit Portfolio
**Scale:** Standard — 2 000 customers · 120 months · 4 scenarios
**Format:** Parquet files in `data_out/`
**Total tables:** 3

---

## What this dataset models

The commercial trade-receivables function of an Oil & Gas company. The company sells petroleum products, LNG, chemicals, and other goods to customers on credit. This dataset tracks:

- Who the customers are and their creditworthiness
- What macro and commodity environment the company operates in
- How much each customer owes, how overdue it is, and what credit controls are in place

---

## The four scenarios

Every time-series table carries a `scenario_id` column:

| Scenario | What it represents | Key shock |
|---|---|---|
| `baseline` | Normal operating environment | Brent ~$75, GDP ~3%, spreads normal |
| `severe_demand` | Global recession | GDP falls 4.6%, Brent drops 35%, credit spreads spike |
| `geopolitical_supply` | Middle East or Russia supply disruption | Brent spikes 50%, gas prices spike 70%, shipping doubles |
| `disorderly_transition` | Abrupt energy-transition repricing | Carbon price triples, long-run Brent falls 20% |

---

## Table overview

| Table | Rows (standard) | One row = | Updated |
|---|---:|---|---|
| `customer_dim` | 2 000 | One O&G buyer | Static |
| `macro_scenario_m` | 480 | One month × one scenario | Monthly |
| `trade_credit_terms_m` | 960 000 | One customer's AR position for one month × scenario | Monthly |

---

## `customer_dim` — The companies that buy from the O&G company

One row per customer. Static — set once at generation time.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `customer_id` | Customer code | Unique identifier | `CST000042` |
| `customer_type` | Buyer type | What kind of company this customer is | `refiner` |
| `sector` | Industry sector | Broad sector classification | `refining_marketing` |
| `country` | Country | Where the customer is headquartered | `US`, `NO`, `SA` |
| `region` | World region | Broader geographic grouping | `North_America` |
| `external_rating` | Credit rating | External agency rating or equivalent estimate | `BBB`, `BB+`, `A-` |
| `commodity_risk_flag` | Commodity-correlated? | `True` if this customer's ability to pay is correlated with oil/gas prices (e.g. an upstream producer whose revenue falls when prices fall) | `True` |
| `connected_party_flag` | Related party? | `True` if this customer has a connected-party relationship with the company | `False` |
| `kyc_status` | KYC status | Know-Your-Customer screening result | `approved`, `pending`, `flagged` |
| `sanctions_flag` | Sanctions? | `True` if this customer appears on a restricted/sanctioned entity list | `False` |
| `annual_revenue_est_usd_m` | Estimated revenue (USD m) | Estimated annual revenue, used for limit calibration | `1 250.0` |

### Customer types

| Type | What they do | Typical products bought |
|---|---|---|
| `commodity_trader` | Trade physical commodities globally | Crude oil, LNG, gas, products |
| `noc` | State-owned national oil company buyer | Crude oil, LNG, gas |
| `independent_producer` | Independent upstream O&G company | Gas, naphtha |
| `refiner` | Refinery operator | Crude oil, naphtha, diesel |
| `utility` | Power and gas utility | LNG, natural gas, power |
| `petrochemical` | Chemical manufacturer | Naphtha, chemicals |
| `shipping` | Vessel operator / charterer | Bunker fuel, crude oil |
| `corporate_buyer` | Industrial end-user | Diesel, natural gas |

---

## `macro_scenario_m` — Monthly market environment

One row per month per scenario (480 rows at standard scale).

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `scenario_id` | Scenario | Which macro scenario this row belongs to | `baseline` |
| `as_of_month` | Month end date | Last calendar day of the month | `2016-01-31` |
| `brent_usd_bbl` | Brent crude ($/bbl) | International oil benchmark price | `73.2` |
| `henry_hub_usd_mmbtu` | Henry Hub gas ($/MMBtu) | US natural gas benchmark | `3.4` |
| `ttf_usd_mmbtu` | TTF gas ($/MMBtu) | European gas benchmark (Title Transfer Facility) | `10.5` |
| `jkm_usd_mmbtu` | JKM LNG ($/MMBtu) | Asian LNG spot price benchmark | `12.1` |
| `global_gdp_yoy` | Global GDP growth (%) | Year-on-year global GDP growth rate | `3.0` |
| `us_gdp_yoy` | US GDP growth (%) | US year-on-year GDP growth | `2.5` |
| `eu_gdp_yoy` | EU GDP growth (%) | EU year-on-year GDP growth | `1.5` |
| `uk_gdp_yoy` | UK GDP growth (%) | UK year-on-year GDP growth | `1.5` |
| `unemployment_us` | US unemployment (%) | US civilian unemployment rate | `4.1` |
| `bbb_spread_bps` | BBB credit spread (bps) | Investment-grade credit market stress indicator | `155` |
| `carbon_price_usd_tco2` | Carbon price ($/tCO₂) | Carbon allowance/offset price | `51.2` |
| `usd_index` | USD index | US dollar strength index | `103.5` |
| `shipping_cost_index` | Shipping cost index | Freight cost index (baseline = 100) | `98.0` |

---

## `trade_credit_terms_m` — Monthly AR ageing and credit controls

One row per customer per month per scenario. This is the core table.

**Grain:** (`customer_id`, `as_of_month`, `scenario_id`)

### Identity and timing

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `customer_id` | Customer code | Links to `customer_dim` | `CST000042` |
| `as_of_month` | Month end date | Date of this AR snapshot | `2018-06-30` |
| `scenario_id` | Scenario | Which macro scenario | `baseline` |
| `last_credit_review_date` | Last review date | Date of the most recent credit limit review | `2018-01-31` |
| `next_review_due_date` | Next review date | Scheduled date for the next credit review | `2019-01-31` |

### Credit limits

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `payment_terms_days` | Payment terms (days) | Number of days from invoice date to payment due date | `30` |
| `approved_credit_limit_usd_m` | Approved limit (USD m) | Maximum credit exposure the company will accept from this customer | `12.5` |
| `temporary_credit_limit_usd_m` | Temporary limit (USD m) | Approved limit plus any short-term temporary increase; may be NaN if not recorded | `13.5` |

### AR ageing buckets

All AR amounts are in USD millions. Buckets are mutually exclusive and sum to `current_ar_usd_m`.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `current_ar_usd_m` | Total AR (USD m) | Total outstanding receivables from this customer | `8.3` |
| `ar_not_due_usd_m` | Not yet due (USD m) | AR from recent deliveries, within payment terms — not yet overdue | `5.1` |
| `ar_1_30_dpd_usd_m` | 1–30 days overdue (USD m) | AR that is 1 to 30 days past the due date | `1.8` |
| `ar_31_60_dpd_usd_m` | 31–60 days overdue (USD m) | AR that is 31 to 60 days past due | `0.9` |
| `ar_61_90_dpd_usd_m` | 61–90 days overdue (USD m) | AR that is 61 to 90 days past due | `0.4` |
| `ar_90_plus_dpd_usd_m` | 90+ days overdue (USD m) | AR more than 90 days past due — highest risk of non-payment | `0.1` |

### Utilisation

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `utilisation_pct` | Utilisation (%) | Total AR as a percentage of approved credit limit (`current_ar / limit × 100`); capped at 200% | `66.4` |

### Credit control flags

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `credit_hold_flag` | Credit hold? | `True` if deliveries have been paused because overdue AR exceeds the hold threshold | `False` |
| `blocked_order_flag` | Blocked orders? | `True` if new orders are blocked because the 90+ DPD bucket exceeds 10% of the credit limit | `False` |

**How credit holds work:**
A credit hold is triggered when `total_overdue / approved_limit > hold_threshold`. It is released (cured) when the ratio falls below half the hold threshold. Hold thresholds: Tier 1 = 25%, Tier 2 = 20%, Tier 3 = 18%, Tier 4 = 15%.

### Risk mitigants

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `letter_of_credit_flag` | Letter of credit? | `True` if a bank letter of credit is in place covering this customer's exposure | `True` |
| `guarantee_flag` | Guarantee? | `True` if a parent company or third-party guarantee is in place | `False` |
| `credit_insurance_flag` | Credit insurance? | `True` if trade credit insurance covers this exposure | `False` |
| `collateral_required_flag` | Collateral posted? | `True` if the customer has posted physical or cash collateral | `False` |
| `collateral_value_usd_m` | Collateral value (USD m) | Estimated value of posted collateral; zero if no collateral | `0.0` |

---

## How to use the data

### Load all data for one scenario

```python
import pandas as pd

ar = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    filters=[("scenario_id", "=", "baseline")]
)
customers = pd.read_parquet("data_out/customer_dim.parquet")
macro = pd.read_parquet(
    "data_out/macro_scenario_m.parquet",
    filters=[("scenario_id", "=", "baseline")]
)
```

### Compute overdue rate by customer type

```python
ar_with_type = ar.merge(customers[["customer_id", "customer_type"]], on="customer_id")

ar_with_type["overdue_usd_m"] = (
    ar_with_type["ar_1_30_dpd_usd_m"]
    + ar_with_type["ar_31_60_dpd_usd_m"]
    + ar_with_type["ar_61_90_dpd_usd_m"]
    + ar_with_type["ar_90_plus_dpd_usd_m"]
)
ar_with_type["overdue_rate"] = (
    ar_with_type["overdue_usd_m"]
    / ar_with_type["current_ar_usd_m"].clip(lower=0.001)
)

print(ar_with_type.groupby("customer_type")["overdue_rate"].mean().sort_values(ascending=False).round(3))
```

### Compare credit hold frequency across scenarios

```python
ar = pd.read_parquet("data_out/trade_credit_terms_m.parquet")

hold_rate = (
    ar.groupby(["scenario_id", "as_of_month"])["credit_hold_flag"]
    .mean() * 100
)
print(hold_rate.unstack("scenario_id").tail(6).round(1))
```

### Identify customers approaching credit hold threshold

```python
ar_latest = ar[ar["as_of_month"] == ar["as_of_month"].max()].copy()
ar_latest["overdue_pct_of_limit"] = (
    (ar_latest["ar_1_30_dpd_usd_m"]
     + ar_latest["ar_31_60_dpd_usd_m"]
     + ar_latest["ar_61_90_dpd_usd_m"]
     + ar_latest["ar_90_plus_dpd_usd_m"])
    / ar_latest["approved_credit_limit_usd_m"].clip(lower=0.001) * 100
)
near_hold = ar_latest[
    (ar_latest["overdue_pct_of_limit"] > 10)
    & (~ar_latest["credit_hold_flag"])
].sort_values("overdue_pct_of_limit", ascending=False)

print(near_hold[["customer_id", "overdue_pct_of_limit", "current_ar_usd_m"]].head(10))
```
