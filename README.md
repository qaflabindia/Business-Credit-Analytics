# Credit Analytics — Synthetic O&G Business AR Dataset Generator

A fully reproducible, scenario-aware synthetic dataset generator for the **Oil & Gas business accounts-receivable (AR) credit function**, calibrated to a Shell-like energy company's commercial credit team.

Generates **3 parquet tables** covering the complete commercial trade-receivables book — customer master, macro/commodity environment, and monthly AR ageing — for use in credit limit management, AR monitoring, collections analytics, and stress testing.

---

## What this is

A Python package that generates realistic, internally consistent synthetic commercial credit data for an oil and gas company's AR function. It is not a sample of real company data. Every number is generated from calibrated statistical models, economic equations, and scenario overlays.

**Use it to:**
- Build and test AR ageing models and credit-limit optimisation tools
- Design and prototype commercial credit dashboards and collections surveillance
- Stress-test AR workflows against four macro and commodity scenarios
- Train commercial credit analysts on a realistic dataset with known ground truth
- Benchmark collections and credit-hold model implementations

**Do not use it to:**
- Make real credit decisions about real companies
- File regulatory returns or submissions
- Represent it as observed market data in any publication or model validation

---

## Quick start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Generate the lite dataset — 500 customers, 36 months, ~5 seconds
python main.py --scale lite --out data_out

# 3. Generate the standard dataset — 2 000 customers, 120 months, ~30 seconds
python main.py --scale standard --out data_out
```

Load any table in Python:

```python
import pandas as pd

customers = pd.read_parquet("data_out/customer_dim.parquet")
ar = pd.read_parquet("data_out/trade_credit_terms_m.parquet",
                     filters=[("scenario_id", "=", "baseline")])
```

---

## Dataset scales

| Scale | Customers | Months | Scenarios | Approx. time | Approx. size |
|---|---:|---:|---|---:|---:|
| `lite` | 500 | 36 | 2 | < 5 s | 2 MB |
| `standard` | 2 000 | 120 | 4 | ~30 s | 25 MB |
| `research` | 8 000 | 180 | 4 | ~5 min | 350 MB |

---

## The three output tables

| Table | What it contains |
|---|---|
| `customer_dim` | One row per customer — type, sector, country, rating, commodity risk flag, KYC status |
| `macro_scenario_m` | Monthly commodity prices and economic indicators per scenario |
| `trade_credit_terms_m` | Monthly AR ageing buckets, credit limits, holds, blocked orders, and risk mitigants per customer |

---

## The four scenarios

Every time-series table carries a `scenario_id` column:

| Scenario | Economic narrative | Key shock |
|---|---|---|
| `baseline` | Orderly operating environment | Brent ~$75, GDP ~3%, spreads ~150 bps |
| `severe_demand` | Global recession | GDP −4.6%, Brent −35%, spreads +250 bps |
| `geopolitical_supply` | Middle East / Russia supply disruption | Brent +50%, TTF +70%, shipping costs +80% |
| `disorderly_transition` | Abrupt energy transition repricing | Carbon price ×2.5, long-run Brent −20% |

---

## Directory structure

```
Credit Analytics/
│
├── main.py                          ← CLI entry point
├── requirements.txt                 ← Python dependencies
│
├── credit_analytics/                ← Core package
│   ├── config.py                    ← Parameters: ratings, regions, seeds, macro baseline
│   ├── pipeline.py                  ← Orchestration: generates, validates, writes
│   ├── noise.py                     ← Controlled AR data-quality imperfections
│   ├── validation.py                ← 8 automated correctness checks
│   │
│   └── generators/
│       ├── calendar.py              ← Date ranges (monthly)
│       ├── macro.py                 ← Correlated AR(1) macro/commodity paths
│       ├── counterparties.py        ← Customer profiles (8 O&G buyer types)
│       └── trade_credit.py          ← Monthly AR ageing, limits, holds, mitigants
│
├── data_out/                        ← Generated parquet files (created by main.py)
│
├── README.md                        ← This file
├── GETTING_STARTED.md               ← Step-by-step setup and first analysis
├── ARCHITECTURE.md                  ← System design and component diagram
├── FUNCTIONAL_SPEC.md               ← Business requirements and acceptance criteria
├── TECHNICAL_SPEC.md                ← Mathematical models and parameters
├── SECURE_DESIGN.md                 ← Data governance and compliance guidance
└── DATA_DICTIONARY.md               ← Column-by-column plain-English reference
```

---

## Validation

Every run automatically executes 8 correctness checks:

```
VALIDATION SUMMARY
  Passed:   8
  Failed:   0
  Warnings: 0

PASSED:
  + bucket_consistency
  + credit_limits_positive
  + credit_limits_bounded
  + utilisation_distribution (zero_AR=0.0%)
  + utilisation_cap (over_150pct=0.0%)
  + hold_overdue_correlation (hold=33.91% > no_hold=3.67%)
  + commodity_risk_check (risk=21.76% >= safe=19.60%)
  + payment_terms_range (7–90 days)
```

---

## Documentation index

| Document | Purpose | Audience |
|---|---|---|
| `README.md` | Project overview and quick start | Everyone |
| `GETTING_STARTED.md` | Step-by-step setup and first analyses | New users |
| `DATA_DICTIONARY.md` | Every table and column explained in plain English | Analysts, data consumers |
| `ARCHITECTURE.md` | System design, module graph, data flow | Developers |
| `FUNCTIONAL_SPEC.md` | Business requirements, use cases, acceptance criteria | Product owners |
| `TECHNICAL_SPEC.md` | Mathematical models, parameters, algorithms | Quants, model developers |
| `SECURE_DESIGN.md` | Data governance, permitted uses, compliance | Risk, compliance |

---

## Reproducibility

All random generation is fully deterministic:

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

To produce a different draw, change `MASTER_SEED` in `credit_analytics/config.py`.

---

## Dependencies

| Library | Purpose | Version |
|---|---|---|
| `numpy` | Array maths, random generation | ≥ 1.24 |
| `pandas` | DataFrames, time-series operations | ≥ 2.0 |
| `pyarrow` | Parquet read/write, streaming writer | ≥ 12.0 |

No database, no network access, no proprietary libraries required.
