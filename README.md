# Credit Analytics — Synthetic Oil & Gas Credit Portfolio Generator

A fully reproducible, scenario-aware synthetic dataset generator for oil and gas credit analytics, calibrated to a Shell-like integrated supermajor archetype.

Generates **17 parquet tables** across **three distinct credit books** — corporate lending, commercial trade receivables, and commodity trading counterparty — for use in credit scoring, PD/LGD modelling, stress testing, and portfolio monitoring.

---

## What this is

A Python package that generates realistic, internally consistent synthetic credit data for an oil and gas portfolio. It is not a sample of real company data. Every number is generated from calibrated statistical models, economic equations, and scenario overlays described in the accompanying specification (`Credit Analytics.md`).

**Use it to:**
- Build and test PD/LGD/ECL models without needing real confidential data
- Design and prototype credit dashboards and portfolio surveillance tools
- Stress-test credit workflows against four macro scenarios
- Train credit analysts on a realistic dataset with known ground truth
- Benchmark credit model implementations against a common dataset

**Do not use it to:**
- Make real credit decisions about real companies
- File regulatory returns or submissions
- Represent it as observed market data in any publication or model validation

---

## Quick start

```bash
# 1. Install dependencies (all standard scientific Python)
pip install -r requirements.txt

# 2. Generate the lite dataset — 1 000 borrowers, 36 months, ~25 seconds
python main.py --scale lite --out data_out

# 3. Generate the standard dataset — 4 000 borrowers, 120 months, ~10 minutes
python main.py --scale standard --out data_out
```

The output is a directory of `.parquet` files, one per table. Load any table in Python:

```python
import pandas as pd
borrowers = pd.read_parquet("data_out/borrower_dim.parquet")
financials = pd.read_parquet("data_out/borrower_financials_q.parquet",
                             filters=[("scenario_id", "=", "baseline")])
```

---

## Dataset scales

| Scale | Borrowers | Facilities | Months | Scenarios | Approx. time | Approx. size |
|---|---:|---:|---:|---|---:|---:|
| `lite` | 1 000 | ~2 600 | 36 | 2 | 15 s | 25 MB |
| `standard` | 4 000 | ~10 400 | 120 | 4 | 10 min | 443 MB |
| `research` | 15 000 | ~39 000 | 180 | 4 | ~60 min | ~5 GB |

---

## The three credit books

| Book | Tables | What it models |
|---|---|---|
| **Lending** | `borrower_dim`, `facility_dim`, `covenant_def_dim`, `facility_snapshot_m`, `covenant_test_fact`, `default_event_fact`, `recovery_cashflow_fact` | Loans, credit lines, reserves-based lending, covenants, defaults, recoveries |
| **Commercial / trade** | `counterparty_dim`, `trade_credit_terms_m` | Product sales on credit, AR ageing buckets, credit holds, blocked orders |
| **Trading** | `counterparty_dim`, `trading_exposure_m` | Commodity derivative MTM, settlement exposure, PFE, netting, CSA, margin calls |

Plus cross-cutting time-series tables: `borrower_financials_q`, `borrower_operations_m`, `reserves_q`, `hedge_position_m`, `rating_history_m`, `macro_scenario_m`, `transaction_fact`.

---

## The four scenarios

Every time-series table carries a `scenario_id` column:

| Scenario | Economic narrative | Key shock |
|---|---|---|
| `baseline` | Orderly growth environment | Brent ~$75, GDP ~3%, BBB spreads ~150 bps |
| `severe_demand` | Global recession (Fed severely-adverse calibration) | GDP −4.6%, Brent −35%, spreads +250 bps |
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
│   ├── config.py                    ← All parameters: segments, ratings, seeds, scenarios
│   ├── pipeline.py                  ← Orchestration: generates, streams, validates, writes
│   ├── noise.py                     ← Controlled data-quality imperfections
│   ├── validation.py                ← 11 automated correctness checks
│   │
│   └── generators/
│       ├── calendar.py              ← Date ranges (monthly / quarterly)
│       ├── macro.py                 ← Correlated AR(1) macro/commodity paths
│       ├── borrowers.py             ← 7-segment borrower archetypes
│       ├── facilities.py            ← Facility types and covenant definitions
│       ├── financials.py            ← Quarterly P&L and balance sheet
│       ├── operations.py            ← Monthly production, prices, costs
│       ├── reserves.py              ← Quarterly proved-reserve stock-flow
│       ├── hedges.py                ← Commodity hedge programmes and MTM
│       ├── snapshots.py             ← Monthly facility exposure snapshots
│       ├── covenants.py             ← Quarterly covenant test results
│       ├── ratings.py               ← Monthly PD and internal grade
│       ├── defaults.py              ← Monthly hazard model and default events
│       ├── recoveries.py            ← Post-default recovery cash flows and LGD
│       ├── counterparties.py        ← Trading and commercial counterparty profiles
│       ├── trade_credit.py          ← Monthly AR ageing and credit controls
│       └── trading_exposure.py      ← Monthly MTM, PFE, netting, margin
│
├── data_out/                        ← Generated parquet files (created by main.py)
│
├── README.md                        ← This file
├── GETTING_STARTED.md               ← Step-by-step setup and first analysis
├── ARCHITECTURE.md                  ← System design and component diagram
├── FUNCTIONAL_SPEC.md               ← Business requirements and use cases
├── TECHNICAL_SPEC.md                ← Mathematical models and implementation detail
├── SECURE_DESIGN.md                 ← Security, governance, and compliance guidance
└── DATA_DICTIONARY.md               ← Column-by-column plain-English reference
```

---

## Validation

Every run automatically executes 11 correctness checks and prints a summary:

```
VALIDATION SUMMARY
  Passed:   11
  Failed:   0
  Warnings: 0

PASSED:
  ✓ accounting_identities.net_debt
  ✓ accounting_identities.solvency_floor
  ✓ reserve_arithmetic.reserve_life_range
  ✓ reserve_arithmetic.pdp_consistency
  ✓ commodity_signs.ebitda_brent_corr (ρ=0.28)
  ✓ rating_monotonicity (Spearman ρ=1.000)
  ✓ pd_lgd_dependence.mean_lgd=0.13
  ✓ seniority_ordering (secured_LGD=0.09 < unsecured_LGD=0.43)
  ✓ covenant_realism.breach_rate=27.86%
  ✓ missingness_realism
  ✓ no_future_leakage
```

---

## Documentation index

| Document | Purpose | Audience |
|---|---|---|
| `README.md` | Project overview and quick start | Everyone |
| `GETTING_STARTED.md` | Step-by-step setup and first analyses | New users |
| `DATA_DICTIONARY.md` | Every table and column explained in plain English | Analysts, data consumers |
| `ARCHITECTURE.md` | System design, module graph, data flow | Developers, architects |
| `FUNCTIONAL_SPEC.md` | Business requirements, use cases, acceptance criteria | Product owners, model validators |
| `TECHNICAL_SPEC.md` | Mathematical models, parameters, algorithms | Quants, model developers |
| `SECURE_DESIGN.md` | Security controls, data governance, compliance | Risk, compliance, InfoSec |

---

## Reproducibility

All random generation is fully deterministic. The same command always produces the same output:

```python
MASTER_SEED = 20260605
SEEDS = {
    "macro": 20260607, "borrowers": 20260608,
    "facilities": 20260609, "financials": 20260610,
    # ... one seed per generation layer
}
```

To produce a different draw, change `MASTER_SEED` in `credit_analytics/config.py`.

---

## Dependencies

| Library | Purpose | Version |
|---|---|---|
| `numpy` | Array maths, random generation | ≥ 1.24 |
| `pandas` | DataFrames, time-series operations | ≥ 2.0 |
| `scipy` | Sigmoid function (logistic PD model) | ≥ 1.10 |
| `pyarrow` | Parquet read/write, streaming writer | ≥ 12.0 |
| `tqdm` | Progress bars (optional) | ≥ 4.65 |

No database, no network access, no proprietary libraries required.
