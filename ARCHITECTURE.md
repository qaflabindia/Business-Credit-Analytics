# Architecture — Credit Analytics

---

## 1. Design principles

The generator is built around four architectural principles:

1. **Causal ordering.** Every table is generated after the tables it depends on. Macro paths drive financials; financials drive ratings; ratings drive defaults; defaults drive recoveries. There is no circular dependency.

2. **One scenario at a time.** Each scenario is generated completely, streamed to parquet, and freed from memory before the next scenario starts. Peak memory per scenario is under 600 MB for the standard scale.

3. **Vectorised over borrowers.** All computation at each time step is performed across all borrowers simultaneously using NumPy arrays. Python loops iterate over time (120 months or 40 quarters), not over borrowers (4 000). The exception is the post-default recovery module, which is event-driven.

4. **Reproducible by construction.** A master seed deterministically derives one child seed per generation layer. The same seed always produces identical output.

---

## 2. High-level system diagram

```
┌────────────────────────────────────────────────────────────┐
│                    main.py  (CLI)                          │
│   --scale  --scenarios  --borrowers  --months  --out       │
└──────────────────────────┬─────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────┐
│                  pipeline.py  (Orchestrator)               │
│                                                            │
│  1. Calendar      2. Macro        3. Borrowers             │
│  4. Facilities    4b. Counterparties                       │
│  ── for each scenario ──────────────────────────────────── │
│  5. Financials    6. Operations   7. Reserves              │
│  8. Hedges       [free ops_m]                              │
│  8b. Trade credit  8c. Trading exposure                    │
│  9. Snapshots    10. Covenants                             │
│  11. Ratings     [free fin_q]                              │
│  12. Defaults    [free cov, ratings]                       │
│  13. Recoveries  [free snaps, res_q]                       │
│  ── write scenario to parquet, free memory ─────────────── │
│  14. Noise (baseline only)                                 │
│  15. Validation                                            │
│  16. Write static tables                                   │
└──────────────────────────┬─────────────────────────────────┘
                           │
                           ▼
┌────────────────────────────────────────────────────────────┐
│               data_out/  (17 × .parquet files)             │
└────────────────────────────────────────────────────────────┘
```

---

## 3. Module dependency graph

```
config.py  ──── (constants, seeds, segment params, rating maps)
    │
    ├── generators/calendar.py       ← date ranges only; no dependencies
    │
    ├── generators/macro.py          ← needs: calendar
    │       AR(1) correlated paths, scenario overlays
    │
    ├── generators/borrowers.py      ← needs: config (segments, regions)
    │       Segment assignment, initial financial state
    │
    ├── generators/facilities.py     ← needs: borrowers, config
    │       Facility types, commitment sizes, covenant definitions
    │
    ├── generators/counterparties.py ← needs: config (rating maps, regions)
    │       Trading and commercial counterparty profiles
    │
    ├── generators/financials.py     ← needs: borrowers, macro
    │       Quarterly revenue AR process, P&L, balance sheet
    │
    ├── generators/operations.py     ← needs: borrowers, macro
    │       Monthly production, prices, lifting costs
    │
    ├── generators/reserves.py       ← needs: borrowers, operations, financials
    │       Proved-reserve stock-flow identity
    │
    ├── generators/hedges.py         ← needs: borrowers, operations, macro
    │       Hedge programmes, MTM valuation
    │
    ├── generators/trade_credit.py   ← needs: counterparties, macro
    │       AR ageing, credit limits, holds, mitigants
    │
    ├── generators/trading_exposure.py ← needs: counterparties, macro
    │       MTM, PFE, netting, CSA, margin calls
    │
    ├── generators/snapshots.py      ← needs: facilities, borrowers, financials,
    │       reserves, macro                     monthly facility state
    │
    ├── generators/covenants.py      ← needs: facilities, covenant defs, financials,
    │       snapshots                           quarterly covenant tests
    │
    ├── generators/ratings.py        ← needs: borrowers, financials, covenants, macro
    │       Monthly PD equation, grade migration
    │
    ├── generators/defaults.py       ← needs: ratings, snapshots, covenants
    │       Monthly hazard, default events
    │
    └── generators/recoveries.py     ← needs: defaults, facilities, borrowers,
                                               snapshots, reserves, macro
            Recovery cash flows, final LGD

noise.py       ← post-processing: applies 8 imperfection types to baseline tables
validation.py  ← 11 automated correctness checks on baseline output
```

---

## 4. Data flow: from seed to parquet

```
MASTER_SEED
    │
    ├─ seed["macro"]      → macro_scenario_m      (480 rows × 4 scenarios)
    │                            │
    │                            ▼
    ├─ seed["borrowers"]  → borrower_dim           (4 000 rows)
    │                            │
    │                    ┌───────┘
    │                    │
    ├─ seed["facilities"] → facility_dim           (10 415 rows)
    │                      covenant_def_dim        (26 129 rows)
    │
    └─ seed["borrowers"]+1 → counterparty_dim      (2 000 rows)


  For each scenario (4 × sequential):
  ┌─────────────────────────────────────────────────────────────────┐
  │ seed["financials"] → borrower_financials_q    (160 000 rows)   │
  │ seed["operations"] → borrower_operations_m   (480 000 rows)   │  ← freed after reserves + hedges
  │ seed["reserves"]   → reserves_q               (58 520 rows)   │
  │ seed["hedges"]     → hedge_position_m        (115 000 rows)   │
  │ seed["snapshots"]+1 → trade_credit_terms_m   (164 040 rows)   │
  │ seed["snapshots"]+2 → trading_exposure_m     (253 000 rows)   │
  │ seed["snapshots"]  → facility_snapshot_m     (457 555 rows)   │
  │ seed["covenants"]  → covenant_test_fact      (381 501 rows)   │
  │ seed["ratings"]    → rating_history_m        (480 000 rows)   │  ← fin_q freed before this
  │ seed["defaults"]   → default_event_fact        (3 259 rows)   │  ← cov + ratings freed after
  │ seed["recoveries"] → recovery_cashflow_fact   (58 000 rows)   │
  │         ↓ free memory ↓                                       │
  │ Write all tables for this scenario → parquet (streaming)      │
  └─────────────────────────────────────────────────────────────────┘

  After all scenarios:
    noise.py  → inject 8 data-quality imperfections into baseline slice
    validation.py → run 11 checks on baseline tables
    Write static tables: borrower_dim, counterparty_dim, facility_dim, ...
    Write transaction_fact (derived from baseline snapshots)
```

---

## 5. Memory management architecture

The standard scale (4 000 borrowers × 120 months × 4 scenarios) would require ~5 GB if all scenarios were held in memory simultaneously. The pipeline avoids this through three mechanisms:

### 5.1 Scenario streaming

Each scenario is processed entirely, written to parquet via `pyarrow.ParquetWriter` (streaming append), then freed with explicit `del` + `gc.collect()` before the next scenario starts.

### 5.2 Intra-scenario early release

Within each scenario, large DataFrames are freed as soon as they are no longer needed:

```
ops_m (480 000 rows, ~60 MB)  freed immediately after hedges are generated
fin_q (160 000 rows, ~30 MB)  freed immediately after ratings are generated
cov   (381 000 rows, ~50 MB)  freed immediately after defaults are generated
ratings (480 000 rows, ~60 MB) freed after defaults
snaps (457 000 rows, ~60 MB)  freed after recoveries
```

Peak memory per scenario ≈ 300–500 MB.

### 5.3 Baseline retention for validation

After the baseline scenario is freed, key baseline tables are retained in memory (or read back from parquet) for the validation and noise steps. This adds ~200 MB of persistent baseline state that is released after validation.

---

## 6. Parquet streaming writer

Large tables are written using `pyarrow.ParquetWriter` in streaming mode — each scenario's batch is appended to the file as a new row group without loading prior data:

```python
writers: dict[str, pq.ParquetWriter] = {}

def _append(name: str, df: pd.DataFrame):
    table = pa.Table.from_pandas(df, preserve_index=False)
    if name not in writers:
        writers[name] = pq.ParquetWriter(str(out_dir / f"{name}.parquet"), table.schema)
    writers[name].write_table(table)
```

Writers are closed only after all scenarios complete, ensuring the parquet footer is valid.

### Row group layout

The resulting parquet files have one row group per scenario per generator call. This enables efficient filter pushdown when reading:

```python
# Reads only the baseline row group — does not scan the whole file
df = pd.read_parquet("borrower_financials_q.parquet",
                     filters=[("scenario_id", "=", "baseline")])
```

---

## 7. Scenario architecture

Each scenario is an independent path generated by:

1. A shared correlated AR(1) process (same Cholesky factor, same random innovations for baseline)
2. A scenario-specific overlay applied on top — additive shocks in the form of `Δ(variable)` over specified month windows
3. Scenario-specific child seeds (offset from the base seed by `hash(scenario_id) % 10_000`)

This means scenarios share the same underlying borrower population and facility structure, but differ in:
- Macro/commodity paths
- Revenue and margin evolution
- PD levels and rating migrations
- Default events and recovery rates

The scenario child seed offset ensures that stress scenarios are not simply rescaled versions of the baseline — borrower-level random effects are independent across scenarios.

---

## 8. Generator design: vectorised time loops

Each generator follows the same pattern:

```python
# Pre-allocate N-dimensional arrays for all borrowers
state = np.zeros(N)                         # current state
eps   = rng.normal(0, sigma, (N, T))        # all shocks pre-allocated

for t in range(T):                          # T = months or quarters
    state = ar1_update(state, macro[t], eps[:, t])   # vectorised over N
    slices.append(build_dataframe(state, t))          # append month slice

return pd.concat(slices, ignore_index=True)
```

The inner loop is over time (T = 120 months), not over borrowers (N = 4 000). Each time-step operation is fully vectorised over N using NumPy broadcasting. This gives roughly 100–1000× speedup over a naive Python double loop.

---

## 9. Ratings: month-by-month PD computation

The ratings generator is the only module that processes both the time dimension and the borrower dimension simultaneously in a way that cannot be parallelised across time (because of rating inertia). It uses a special architecture:

```python
# Pre-fetch fin_q into a fast lookup dict
fin_index = fin_q.set_index(["borrower_id", "as_of_quarter"])

# One pass per month (120 iterations)
for t, month in enumerate(months):
    qdate = nearest_quarter_end(month)

    # Refresh financial state for all N borrowers when quarter changes
    if qdate != prev_qdate:
        for i, bid in enumerate(borrower_ids):
            lev[i], icr[i], ... = fin_index.loc[(bid, qdate)]

    # Compute PD for all N borrowers — fully vectorised
    logit_pd = alpha_pd + 0.85*z(lev) - 0.95*z(icr) + ... + macro_terms + re
    pd_1y    = expit(logit_pd)

    # Apply one-notch inertia
    delta = raw_grade_idx - current_grade
    new_grade = current_grade + sign(delta) * min(|delta|, 1)
```

The financial state refresh (inner `for i` loop over N borrowers) runs only when the quarter changes — 40 times in 120 months, not 120 times. Each refresh is a pandas MultiIndex lookup and takes ~50 ms for 4 000 borrowers.

---

## 10. Covenant test architecture

The covenant generator uses `DataFrame.explode()` rather than a Cartesian cross-join, to avoid the 1 M-row intermediate:

```
Old approach (cross-join):
  26 129 covenant defs × 40 quarters → 1 045 160 rows intermediate → filter to 381 000
  Peak memory: ~250 MB just for this intermediate

New approach (explode):
  For each covenant, compute list of active quarters during its facility life
  Explode the list column → directly generates 381 000 rows
  Peak memory: ~50 MB
```

---

## 11. Key configuration constants (config.py)

| Constant | What it controls |
|---|---|
| `MASTER_SEED` | Top-level reproducibility seed (default: 20260605) |
| `SEEDS` | One integer seed per generation layer (14 total) |
| `SEGMENTS` | 7 borrower archetypes: shares, financial parameters, commodity betas, PD intercepts |
| `REGIONS` / `REGION_WEIGHTS` | Geographic distribution of borrowers and counterparties |
| `RATING_GRADES` / `RATING_TO_PD` | Standard S&P/Fitch rating scale with long-run average default rates |
| `MACRO_BASELINE` | Starting levels for all 14 macro/commodity variables |
| `SCENARIOS` | List of four scenario identifiers |

---

## 12. Extension points

The architecture is designed to be extended at any layer without touching the pipeline:

| What to extend | Where | How |
|---|---|---|
| Add a new borrower segment | `config.py` → `SEGMENTS` | Add a new key with all required parameters |
| Add a new macro variable | `generators/macro.py` | Add to `_AR_PARAMS` and `_CORR_PAIRS` |
| Add a new facility type | `generators/facilities.py` | Add to `_FACILITY_TYPE_PARAMS` |
| Add a new covenant type | `generators/covenants.py` | Add to `_TEST_SPECS` |
| Add a new table | New file in `generators/` | Write function returning a DataFrame; call from `pipeline.py` |
| Add a new scenario | `config.py` + `generators/macro.py` | Add to `SCENARIOS` list and add overlay logic in `_apply_overlay()` |
| Change the PD model | `generators/ratings.py` | Modify the `logit_pd` equation in the time loop |
| Add a new validation check | `validation.py` | Add a `_check_*` function and call from `validate_all()` |
