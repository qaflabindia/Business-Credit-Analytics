# Getting Started — Credit Analytics

This guide takes you from a clean machine to a working dataset and first analysis in under 15 minutes.

---

## 1. Prerequisites

| Requirement | Minimum version | How to check |
|---|---|---|
| Python | 3.10 | `python3 --version` |
| pip | 21.0 | `pip --version` |
| Free disk space | 500 MB (standard scale) | |
| Free RAM | 4 GB (standard scale) | |

---

## 2. Installation

Clone or copy the project folder, then install the five required Python libraries:

```bash
cd "Credit Analytics"
pip install -r requirements.txt
```

That installs: `numpy`, `pandas`, `scipy`, `pyarrow`, `tqdm`.

No database, no API keys, no network access is needed at runtime.

---

## 3. Generate your first dataset (lite scale)

Start with the lite scale — it runs in about 15 seconds and produces 25 MB of data:

```bash
python main.py --scale lite --out data_out
```

You will see a progress log like this:

```
Pipeline start       scale=lite  borrowers=1,000  months=36  scenarios=['baseline', 'severe_demand']
Calendar             36 months  12 quarters
Macro                72 rows    scenarios=2
Borrowers            1,000 rows
Facilities           2,607 facilities  6,602 covenant defs
Counterparties       500 rows
  → Scenario: baseline
    Financials       12,000 rows
    Operations       36,000 rows
    Reserves          4,716 rows
    Hedges           24,000 rows
    Trade credit     12,636 rows  holds=1,753
    Trading exposure 19,224 rows  breaches=117
    Snapshots        77,631 rows
    Covenants        69,097 rows  breaches=24,824
    Ratings          36,000 rows
    Defaults            605 rows  events=234
    Recoveries       10,454 rows
  → Scenario: severe_demand
    ...
VALIDATION SUMMARY   Passed: 11  Failed: 0  Warnings: 0
Done                 elapsed=14.6s
```

At the end, `data_out/` contains 17 `.parquet` files.

---

## 4. Explore the output

Open a Python session:

```python
import pandas as pd

# List all files
import os
print([f for f in os.listdir("data_out") if f.endswith(".parquet")])

# Look at the borrowers
borrowers = pd.read_parquet("data_out/borrower_dim.parquet")
print(borrowers.shape)                          # (1000, 23)
print(borrowers["segment"].value_counts())

# Quarterly financials — baseline scenario only
fin = pd.read_parquet(
    "data_out/borrower_financials_q.parquet",
    filters=[("scenario_id", "=", "baseline")]
)
print(fin[["revenue_usd_m", "ebitda_usd_m", "net_debt_ebitda_x"]].describe())
```

---

## 5. Generate the standard dataset

The standard scale is what the full dataset design calls for — 4 000 borrowers, 120 months, four scenarios:

```bash
python main.py --scale standard --out data_out
```

This takes roughly 10 minutes and produces ~443 MB. The same 17 tables are generated; each parquet file now contains data for all four scenarios identified by the `scenario_id` column.

To run only a subset of scenarios (faster):

```bash
python main.py --scale standard --scenarios baseline severe_demand --out data_out
```

---

## 6. Load and filter data efficiently

The parquet files support column projection and row-group filtering — you do not need to load everything into memory.

```python
import pandas as pd

# Load only the columns you need
snap = pd.read_parquet(
    "data_out/facility_snapshot_m.parquet",
    columns=["facility_id", "borrower_id", "as_of_month",
             "drawn_usd_m", "ead_usd_m", "stage_ifrs9", "watchlist_flag"],
    filters=[("scenario_id", "=", "baseline")]
)

# Load a specific borrower's financial history
fin = pd.read_parquet(
    "data_out/borrower_financials_q.parquet",
    filters=[
        ("scenario_id", "=", "baseline"),
        ("borrower_id", "=", "BRW000042"),
    ]
)
```

---

## 7. First analyses

### 7a. Default rate by segment

```python
import pandas as pd

borrowers = pd.read_parquet("data_out/borrower_dim.parquet")
defaults  = pd.read_parquet("data_out/default_event_fact.parquet",
                             filters=[("scenario_id", "=", "baseline")])

# Unique defaulted borrowers per segment
def_brw = defaults[["borrower_id", "scenario_id"]].drop_duplicates()
merged  = def_brw.merge(borrowers[["borrower_id", "segment"]], on="borrower_id")

total_by_seg  = borrowers["segment"].value_counts()
def_by_seg    = merged["segment"].value_counts()
default_rate  = (def_by_seg / total_by_seg * 100).sort_values(ascending=False)

print(default_rate.round(1))
```

### 7b. Compare default rates across scenarios

```python
defaults = pd.read_parquet("data_out/default_event_fact.parquet")

# Unique defaulted borrowers per scenario
summary = (defaults
    .groupby("scenario_id")["borrower_id"]
    .nunique()
    .rename("unique_defaulted_borrowers")
    .reset_index())

print(summary.sort_values("unique_defaulted_borrowers"))
```

### 7c. IFRS 9 stage migration over time

```python
snap = pd.read_parquet(
    "data_out/facility_snapshot_m.parquet",
    columns=["as_of_month", "stage_ifrs9", "ead_usd_m", "scenario_id"],
    filters=[("scenario_id", "in", ["baseline", "severe_demand"])]
)

stage_ead = (snap
    .groupby(["scenario_id", "as_of_month", "stage_ifrs9"])["ead_usd_m"]
    .sum()
    .unstack("stage_ifrs9")
    .fillna(0))

print(stage_ead.tail(6))
```

### 7d. Credit holds in the trade book under stress

```python
trade = pd.read_parquet("data_out/trade_credit_terms_m.parquet")

hold_rate = (trade
    .groupby(["scenario_id", "as_of_month"])["credit_hold_flag"]
    .mean() * 100
    .rename("hold_pct"))

print(hold_rate.unstack("scenario_id").tail(6).round(1))
```

### 7e. Portfolio-level expected loss

```python
ratings = pd.read_parquet(
    "data_out/rating_history_m.parquet",
    columns=["borrower_id", "as_of_month", "scenario_id", "internal_pd_1y"]
)
snap    = pd.read_parquet(
    "data_out/facility_snapshot_m.parquet",
    columns=["borrower_id", "as_of_month", "scenario_id", "ead_usd_m"]
)

LGD_ASSUMPTION = 0.45   # average LGD — replace with model output

merged = snap.merge(ratings, on=["borrower_id", "as_of_month", "scenario_id"])
merged["el_usd_m"] = merged["internal_pd_1y"] * LGD_ASSUMPTION * merged["ead_usd_m"]

el_by_scenario = (merged
    .groupby(["scenario_id", "as_of_month"])["el_usd_m"]
    .sum()
    .unstack("scenario_id"))

print(el_by_scenario.tail(4).round(1))
```

---

## 8. CLI reference

```
python main.py [options]

  --scale     lite | standard | research    (default: standard)
  --scenarios baseline severe_demand geopolitical_supply disorderly_transition
              (one or more; default: all four)
  --out       path/to/output/directory      (default: data_out)
  --borrowers N    override the borrower count (overrides --scale)
  --months    N    override the number of months (overrides --scale)
```

Examples:

```bash
# Fast prototype: 500 borrowers, 24 months, baseline only
python main.py --borrowers 500 --months 24 --scenarios baseline --out quick_test

# Standard run with baseline and stress only
python main.py --scale standard --scenarios baseline severe_demand --out data_out

# Research grade (takes ~60 minutes)
python main.py --scale research --out research_data
```

---

## 9. Regenerating with a different random seed

All generation is reproducible from a single master seed. To produce a statistically independent draw (for cross-validation or ensemble work), change `MASTER_SEED` in `credit_analytics/config.py`:

```python
# credit_analytics/config.py
MASTER_SEED = 20260605   # change this integer to get a new draw
```

Each child seed for each generation layer is derived deterministically from the master seed.

---

## 10. Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | Dependencies not installed | Run `pip install -r requirements.txt` |
| Generation killed mid-run (exit 137) | System out of memory | Use `--scale lite` or reduce `--borrowers` |
| Very slow covenants step | Python loop overhead on large scales | Normal for research scale; use `--scale standard` |
| Parquet file shows 0 rows for a scenario | Scenario not included in the run | Re-run including that scenario in `--scenarios` |
| Validation warnings about missingness | Private borrowers have zero missing data | The noise is injected into baseline slices only; filter on `filing_lag_flag` |
| `ArrowInvalid` when reading mid-run | Reading a file while the writer is still open | Wait for the run to complete before reading |

---

## 11. What to read next

| If you want to… | Read… |
|---|---|
| Understand what each column means | `DATA_DICTIONARY.md` |
| Understand the business use cases this supports | `FUNCTIONAL_SPEC.md` |
| Understand the math behind the PD/LGD models | `TECHNICAL_SPEC.md` |
| Understand how the modules connect | `ARCHITECTURE.md` |
| Understand what you can and cannot do with this data | `SECURE_DESIGN.md` |
