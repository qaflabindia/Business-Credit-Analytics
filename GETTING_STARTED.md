# Getting Started — Credit Analytics (O&G Business AR)

This guide takes you from a clean machine to a working dataset and first analysis in under 10 minutes.

---

## 1. Prerequisites

| Requirement | Minimum version | How to check |
|---|---|---|
| Python | 3.10 | `python3 --version` |
| pip | 21.0 | `pip --version` |
| Free disk space | 50 MB (standard scale) | |
| Free RAM | 1 GB (standard scale) | |

---

## 2. Installation

```bash
cd "Credit Analytics"
pip install -r requirements.txt
```

Installs: `numpy`, `pandas`, `pyarrow`. No database, no API keys, no network access required.

---

## 3. Generate your first dataset (lite scale)

Start with the lite scale — it runs in under 5 seconds and produces ~2 MB of data:

```bash
python main.py --scale lite --out data_out
```

You will see output like:

```
Pipeline start                    scale=lite  customers=500  months=36  scenarios=['baseline', 'severe_demand', ...]
Calendar                          36 months
Macro                             144 rows  scenarios=4
Customers                         500 rows  types={'commodity_trader': 91, 'corporate_buyer': 90, ...}
  → Scenario: baseline
    AR                            18,000 rows  holds=2027
  → Scenario: severe_demand
    AR                            18,000 rows  holds=2082
  ...
Noise injection                   applied to baseline AR slice

VALIDATION SUMMARY
  Passed:   8
  Failed:   0
  Warnings: 0

  Wrote customer_dim               500 rows
  Wrote macro_scenario_m           144 rows
  Wrote trade_credit_terms_m    72,000 rows
Done                              elapsed=0.2s
```

`data_out/` now contains 3 `.parquet` files.

---

## 4. Explore the output

```python
import pandas as pd

# List all files
import os
print([f for f in os.listdir("data_out") if f.endswith(".parquet")])
# ['customer_dim.parquet', 'macro_scenario_m.parquet', 'trade_credit_terms_m.parquet']

# Look at the customers
customers = pd.read_parquet("data_out/customer_dim.parquet")
print(customers.shape)                         # (500, 11)
print(customers["customer_type"].value_counts())

# AR table — baseline scenario
ar = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    filters=[("scenario_id", "=", "baseline")]
)
print(ar.shape)                                # (18000, 22)
print(ar[["current_ar_usd_m", "ar_90_plus_dpd_usd_m", "utilisation_pct"]].describe())
```

---

## 5. Generate the standard dataset

```bash
python main.py --scale standard --out data_out
```

Takes ~30 seconds, produces ~25 MB. Generates all four scenarios. Filter by `scenario_id` when loading.

To run only a subset of scenarios:

```bash
python main.py --scale standard --scenarios baseline severe_demand --out data_out
```

---

## 6. Load and filter data efficiently

```python
import pandas as pd

# Load only the columns you need
ar = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    columns=["customer_id", "as_of_month", "scenario_id",
             "current_ar_usd_m", "ar_90_plus_dpd_usd_m",
             "credit_hold_flag", "approved_credit_limit_usd_m"],
    filters=[("scenario_id", "=", "baseline")]
)

# Load a specific customer's AR history
single = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    filters=[
        ("scenario_id", "=", "baseline"),
        ("customer_id", "=", "CST000042"),
    ]
)
```

---

## 7. First analyses

### 7a. Overdue rate by customer type

```python
import pandas as pd

customers = pd.read_parquet("data_out/customer_dim.parquet")
ar = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    filters=[("scenario_id", "=", "baseline")]
)

ar = ar.merge(customers[["customer_id", "customer_type"]], on="customer_id")
ar["overdue_rate"] = (
    ar["ar_1_30_dpd_usd_m"] + ar["ar_31_60_dpd_usd_m"]
    + ar["ar_61_90_dpd_usd_m"] + ar["ar_90_plus_dpd_usd_m"]
) / ar["current_ar_usd_m"].clip(lower=0.001)

print(ar.groupby("customer_type")["overdue_rate"].mean().sort_values(ascending=False).round(3))
```

### 7b. Credit hold frequency across scenarios

```python
ar = pd.read_parquet("data_out/trade_credit_terms_m.parquet")

hold_rate = (
    ar.groupby(["scenario_id", "as_of_month"])["credit_hold_flag"]
    .mean() * 100
    .rename("hold_pct")
)
print(hold_rate.unstack("scenario_id").tail(6).round(1))
```

### 7c. AR at risk — 90+ DPD by scenario

```python
ar = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    columns=["scenario_id", "as_of_month", "ar_90_plus_dpd_usd_m"]
)

risk = ar.groupby(["scenario_id", "as_of_month"])["ar_90_plus_dpd_usd_m"].sum()
print(risk.unstack("scenario_id").tail(6).round(1))
```

### 7d. Customers near credit hold threshold

```python
ar = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    filters=[("scenario_id", "=", "baseline")]
)

latest = ar.sort_values("as_of_month").groupby("customer_id").last().reset_index()
latest["overdue_pct"] = (
    (latest["ar_1_30_dpd_usd_m"] + latest["ar_31_60_dpd_usd_m"]
     + latest["ar_61_90_dpd_usd_m"] + latest["ar_90_plus_dpd_usd_m"])
    / latest["approved_credit_limit_usd_m"].clip(lower=0.001) * 100
)

near_hold = latest[
    (latest["overdue_pct"] > 10) & (~latest["credit_hold_flag"])
].sort_values("overdue_pct", ascending=False)

print(near_hold[["customer_id", "overdue_pct", "current_ar_usd_m"]].head(10).round(2))
```

### 7e. Commodity-risk vs safe customer overdue rates

```python
customers = pd.read_parquet("data_out/customer_dim.parquet")
ar = pd.read_parquet(
    "data_out/trade_credit_terms_m.parquet",
    filters=[("scenario_id", "=", "severe_demand")]
)

ar = ar.merge(customers[["customer_id", "commodity_risk_flag"]], on="customer_id")
ar["overdue_rate"] = (
    ar["ar_1_30_dpd_usd_m"] + ar["ar_31_60_dpd_usd_m"]
    + ar["ar_61_90_dpd_usd_m"] + ar["ar_90_plus_dpd_usd_m"]
) / ar["current_ar_usd_m"].clip(lower=0.001)

print(ar.groupby("commodity_risk_flag")["overdue_rate"].mean().round(3))
```

---

## 8. CLI reference

```
python main.py [options]

  --scale      lite | standard | research     (default: standard)
  --scenarios  baseline severe_demand geopolitical_supply disorderly_transition
               (one or more; default: all four)
  --out        path/to/output/directory       (default: data_out)
  --customers  N    override customer count (overrides --scale)
  --months     N    override number of months (overrides --scale)
```

Examples:

```bash
# Quick prototype: 200 customers, 24 months, baseline only
python main.py --customers 200 --months 24 --scenarios baseline --out quick_test

# Standard run with baseline and stress only
python main.py --scale standard --scenarios baseline severe_demand --out data_out

# Research scale (takes ~5 minutes)
python main.py --scale research --out research_data
```

---

## 9. Regenerating with a different random seed

To produce a statistically independent draw, change `MASTER_SEED` in `credit_analytics/config.py`:

```python
# credit_analytics/config.py
MASTER_SEED = 20260605   # change this integer to get a new draw
```

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -r requirements.txt` |
| `KeyError: 'policy_rate_bps'` | Stale old parquet files in `data_out/` | Delete `data_out/` and regenerate |
| Parquet file shows 0 rows for a scenario | Scenario not included in the run | Re-run including that scenario in `--scenarios` |
| `ArrowInvalid` when reading mid-run | Reading a file while the writer is still open | Wait for the run to complete before reading |

---

## 11. What to read next

| If you want to… | Read… |
|---|---|
| Understand what each column means | `DATA_DICTIONARY.md` |
| Understand the business use cases | `FUNCTIONAL_SPEC.md` |
| Understand the AR ageing math | `TECHNICAL_SPEC.md` |
| Understand how the modules connect | `ARCHITECTURE.md` |
| Understand permitted uses | `SECURE_DESIGN.md` |
