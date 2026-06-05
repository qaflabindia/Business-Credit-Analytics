# Technical Specification — Credit Analytics

**Document type:** Technical Specification
**Status:** Active
**Version:** 1.0
**Covers:** Mathematical models, generation algorithms, parameters, performance

---

## 1. Reproducibility and random number generation

### 1.1 Seed architecture

```python
MASTER_SEED = 20260605

SEEDS = {
    "calendar":    20260606,   # date ranges
    "macro":       20260607,   # AR(1) macro paths
    "borrowers":   20260608,   # borrower archetypes
    "facilities":  20260609,   # facility origination
    "financials":  20260610,   # quarterly P&L
    "operations":  20260611,   # monthly production
    "reserves":    20260612,   # proved reserves
    "hedges":      20260613,   # hedge programmes
    "snapshots":   20260614,   # facility snapshots
    "covenants":   20260615,   # covenant tests
    "ratings":     20260616,   # rating model
    "defaults":    20260617,   # default simulation
    "recoveries":  20260618,   # recovery cash flows
    "dq_noise":    20260619,   # data quality injection
}
```

Each scenario receives a scenario-specific child seed offset:
```python
child_seed = SEEDS["financials"] + hash(scenario_id) % 10_000
rng = np.random.default_rng(child_seed)
```

All RNG calls use NumPy's PCG64-based `default_rng`, which is the current NumPy recommendation for reproducible scientific computation.

---

## 2. Macro scenario model

### 2.1 Correlated AR(1) process

Each macro variable follows a mean-reverting AR(1) process:

```
X_t = μ_t × (1 − ρ) + ρ × X_{t−1} + σ × ε_t
```

where `ε_t` are correlated standard normal innovations generated via Cholesky decomposition of the correlation matrix:

```
ε = Z × L^T    where Z ~ N(0, I) and Σ = L × L^T
```

### 2.2 Variable parameters

| Variable | Baseline level (μ) | Persistence (ρ) | Monthly vol (σ) | Monthly trend |
|---|---:|---:|---:|---:|
| `brent_usd_bbl` | 75.0 | 0.85 | 7.0 | — |
| `henry_hub_usd_mmbtu` | 3.5 | 0.80 | 0.45 | — |
| `ttf_usd_mmbtu` | 10.0 | 0.80 | 1.20 | — |
| `jkm_usd_mmbtu` | 12.0 | 0.80 | 1.60 | — |
| `global_gdp_yoy` | 3.0 | 0.70 | 0.70 | — |
| `us_gdp_yoy` | 2.5 | 0.75 | 0.80 | — |
| `eu_gdp_yoy` | 1.5 | 0.70 | 0.65 | — |
| `uk_gdp_yoy` | 1.5 | 0.70 | 0.70 | — |
| `unemployment_us` | 4.0 | 0.92 | 0.25 | — |
| `bbb_spread_bps` | 150.0 | 0.88 | 18.0 | — |
| `policy_rate_bps` | 450.0 | 0.95 | 12.0 | — |
| `carbon_price_usd_tco2` | 50.0 | 0.90 | 4.0 | +0.40/month |
| `usd_index` | 103.0 | 0.90 | 1.20 | — |
| `shipping_cost_index` | 100.0 | 0.80 | 8.0 | — |

### 2.3 Key pairwise correlations

| Variable pair | Correlation |
|---|---:|
| Brent ↔ Henry Hub | +0.40 |
| Brent ↔ TTF | +0.45 |
| Brent ↔ JKM | +0.50 |
| TTF ↔ JKM | +0.70 |
| Brent ↔ global GDP | +0.35 |
| Global GDP ↔ US GDP | +0.80 |
| US GDP ↔ unemployment | −0.75 |
| BBB spread ↔ global GDP | −0.50 |
| BBB spread ↔ Brent | −0.30 |
| BBB spread ↔ unemployment | +0.60 |
| Brent ↔ USD index | −0.35 |
| Brent ↔ shipping costs | +0.45 |

### 2.4 Scenario overlays

Overlays are additive or multiplicative shocks applied on top of the AR(1) baseline path over specified month windows:

| Scenario | Window | Key shocks |
|---|---|---|
| `severe_demand` | Months 30–60 (peak at 42) | US GDP −4.6%, BBB spread +250 bps, Brent ×0.65, policy rate −200 bps |
| `geopolitical_supply` | Months 45–72 (peak at 54) | Brent ×1.50, TTF ×1.70, JKM ×1.60, shipping ×1.80 |
| `disorderly_transition` | Months 60–120 (gradual) | Brent ×0.80, carbon ×2.50, BBB spread +50 bps |

---

## 3. Borrower financial model

### 3.1 Revenue AR process (quarterly)

Log-revenue follows a panel AR(1) with macro factor loadings:

```
ln(Revenue_{i,q}) = ln(Revenue_{i,q−1})
                  + μ_segment
                  + β_oil,segment × Δln(Brent_q)
                  + β_gas,segment × Δln(Gas_q)
                  + β_gdp,segment × (GDP_q / 100)
                  + ε_{i,q}
```

where `ε_{i,q} ~ N(0, 0.04)` is idiosyncratic noise.

Segment-specific betas:

| Segment | β_oil | β_gas | β_gdp | μ (quarterly) |
|---|---:|---:|---:|---:|
| supermajor | 0.40 | 0.15 | 0.05 | 0.010 |
| large_integrated | 0.45 | 0.18 | 0.06 | 0.008 |
| independent_upstream | 0.70 | 0.30 | 0.03 | 0.005 |
| midstream_lng | 0.20 | 0.50 | 0.08 | 0.006 |
| refining_marketing | −0.30 | 0.10 | 0.15 | 0.004 |
| oilfield_services | 0.35 | 0.15 | 0.12 | 0.003 |
| trading_petrochemicals | 0.25 | 0.20 | 0.18 | 0.005 |

### 3.2 EBITDA margin model

```
Margin_{i,q} = clip(
    Margin_{i,q−1}
    + 0.25 × price_shock
    − 0.15 × lifting_cost_shock
    + 0.05 × hedge_cushion
    + ν_{i,q},
    0.01, 0.85
)

where:
  price_shock      = 0.40 × Δln(Brent_q) + 0.20 × Δln(Gas_q)
  lifting_cost_shock = 0.15 × (inflation − 4.5%) / 100
  hedge_cushion    = hedge_ratio_i × |Δln(Brent_q)|
  ν_{i,q}         ~ N(0, 0.015)
```

### 3.3 Balance sheet identities

```
EBITDA_q = Revenue_q × Margin_q
DA_q     = Revenue_q × 0.12
EBIT_q   = EBITDA_q − DA_q
GrossDebt_q = leverage_q × EBITDA_q × 4        (annualised)
Interest_q  = GrossDebt_q × 0.06
EBT_q    = EBIT_q − Interest_q
Tax_q    = max(EBT_q × 0.25, 0)
CFO_q    = EBITDA_q − Interest_q − Tax_q + DA_q × 0.30
Capex_q  = Revenue_q × capex_rate            (0.25 upstream, 0.08 others)
Cash_q   = max(GrossDebt_q × 0.05, GrossDebt_q × 0.10 + (CFO_q − Capex_q) × 0.5)
NetDebt_q = GrossDebt_q − Cash_q
```

Leverage is updated each quarter:
```
Leverage_q = clip(NetDebt_q / max(EBITDA_q × 4, 1), 0.05, 20.0)
```

---

## 4. Reserve model (upstream borrowers only)

### 4.1 Stock-flow identity

```
ProvedReserves_q = ProvedReserves_{q−1}
                 − Production_q             (kboed × 91 days / 1 000)
                 + ExtensionsDiscoveries_q   (Capex_q / FnDCost_q / 4)
                 + AcquisitionsDivestments_q (random, sparse: P = 0.02)
                 + NetRevisions_q            (price-driven + random)

NetRevisions_q = ProvedReserves_{q−1} × 0.05 × (Brent_q / 75 − 1)
               + N(0, 2)

FnDCost_q ~ U(15, 25)   USD/boe
```

### 4.2 Reserve sub-category split

```
PDP  = ProvedReserves × pdp_share_i         where pdp_share_i ~ U(0.50, 0.70)
PDNP = ProvedReserves × U(0.05, 0.15)
PUD  = ProvedReserves − PDP − PDNP
```

### 4.3 Reserve life

```
ReserveLife_q = ProvedReserves_q / max(Production_q × 4, ε)   years
```

---

## 5. Production model

### 5.1 Field decline AR(1) with capex boost

```
Production_{i,t} = Production_{i,t−1}
                 × (1 − δ_decline + δ_capex)
                 × outage_mult_{i,t}
                 × (1 + ε_{i,t})

where:
  δ_decline   = 0.003    monthly natural decline rate (~3.5% pa)
  δ_capex     = 0.005    capex-driven partial offset
  outage_mult = 1 − planned_days/30 − unplanned_days/30   (clipped to [0.7, 1.0])
  ε_{i,t}    ~ N(0, 0.03)
```

Initial production is lognormal within each segment:
```
Production_{i,0} = exp(ln(median_kboed_segment) + N(0, 0.50))
```

---

## 6. Probability of default model

### 6.1 Point-in-time PD equation

```
logit(PD1Y_{i,t}) =
      α_segment
    + 0.85 × z(Leverage_{i,t})
    − 0.95 × z(InterestCoverage_{i,t})
    − 0.50 × z(CashRatio_{i,t})
    + 0.25 × z(DecommBurden_{i,t})
    − 0.20 × z(ReserveLife_{i,t})
    − 0.30 × HedgeRatio_i
    − 0.40 × CovenantHeadroom (population mean proxy: 0.15)
    + 0.50 × z(BBBspread_t)
    − 0.55 × z(GDP_t)
    − 0.80 × β_commodity_i × z(Brent_t)
    + RE_borrower_i                        ~ N(0, 0.40)
    + RE_time_t                            ~ N(0, 0.15)

PD1Y_{i,t} = expit(logit_pd)   clipped to [0.00001, 0.999]
```

where `z(x)` denotes cross-sectional standardisation at each time step:
```
z(x_t) = (x_{i,t} − mean_t(x)) / max(std_t(x), 0.001)
```

### 6.2 Segment PD intercepts (α_segment)

| Segment | α (logit scale) | Approx. baseline median PD |
|---|---:|---:|
| supermajor | −5.80 | 0.03% |
| large_integrated | −4.60 | 0.10% |
| midstream_lng | −3.80 | 0.22% |
| refining_marketing | −4.00 | 0.18% |
| trading_petrochemicals | −4.20 | 0.15% |
| oilfield_services | −3.50 | 0.30% |
| independent_upstream | −3.20 | 0.40% |

### 6.3 Rating grade inertia

To prevent unrealistic grade volatility, ratings move by at most one notch per month:

```
Δgrade = raw_grade_idx_t − grade_{t−1}
grade_t = grade_{t−1} + sign(Δgrade) × min(|Δgrade|, 1)
```

---

## 7. Default simulation model

### 7.1 Monthly hazard rate

```
MonthlyHazard_{i,t} = 1 − exp(−PD1Y_{i,t} / 12)
```

Hazard is uplifted for covenant breaches and DPD:

```
if breach_count_i > 0:    hazard = min(hazard × (1 + 0.3 × breach_count), 1.0)
if DPD ≥ 30:              hazard = min(hazard × 1.5, 1.0)
if DPD ≥ 60:              hazard = min(hazard × 2.0, 1.0)
if DPD ≥ 90:              hazard = 1.0   (automatic default trigger)
```

### 7.2 Default event

```
Default_{i,t} ~ Bernoulli(MonthlyHazard_{i,t})    for non-defaulted borrowers
```

Once a borrower defaults, it enters a 24-month resolution window during which it cannot re-default.

### 7.3 Default type assignment

| Type | Condition | Probability conditional on default |
|---|---|---|
| `dpd_90` | DPD ≥ 90 | Automatic |
| `bankruptcy` | DPD < 90 and random draw | 30% |
| `distressed_restructuring` | DPD < 90 and not bankruptcy | 40% |
| `unlikely_to_pay` | Remaining | 30% |

---

## 8. Recovery model

### 8.1 Recovery rate equation

```
logit(RR_j) =
      0.50                                    (intercept)
    + 0.60 × CollateralCoverage_j
    + 0.80 × SecuredFlag_j                   (1 if senior secured)
    + 0.40 × PDPshare_j                      (PDP / total proved reserves)
    + 0.30 × HedgeRatio_j
    − 0.50 × min(DecommBurden_j, 3.0)
    − 0.45 × z(BBBspread_t)
    − 0.35 × IndustryDefaultRate             (fixed proxy: 0.03)
    − 0.25 × z(ResolutionTime_j)             (months, normalised)
    + ω_j                                    ~ N(0, 0.30)

RR_j = expit(logit_rr)

LGD_j = 1 − RR_j
```

Recovery rates are additionally clipped by seniority:

| Seniority | RR floor | RR cap |
|---|---:|---:|
| `senior_secured` | 10% | 95% |
| `senior_unsecured` | 5% | 80% |
| `subordinated` | 1% | 60% |

### 8.2 Resolution timing

```
ResolutionMonths_j ~ clip(N(μ_seniority, 6), 6, 48)

where:
  μ(senior_secured)   = 18 months
  μ(senior_unsecured) = 24 months
  μ(subordinated)     = 32 months
```

### 8.3 Cash flow profile

Recovery cash flows are distributed over the resolution period with a back-loaded profile:

```
weights = linspace(0.5, 2.0, n_months)
weights /= sum(weights)
monthly_net_recovery = total_net_recovery × weights
```

---

## 9. Trading exposure model

### 9.1 Mark-to-market

```
MTM_positive_{c,k,t} = max(0, position_{c,k} × price_change_pct_{k,t} × notional_{c,k})
MTM_negative_{c,k,t} = max(0, −position_{c,k} × price_change_pct_{k,t} × notional_{c,k})

price_change_pct_{k,t} = (CurrentPrice_{k,t} − EntryPrice_{k,0}) / EntryPrice_{k,0}
```

### 9.2 Netting

For counterparties with `netting_agreement_flag = True`:
```
NetMTMPositive = MTMPositive × 0.35
NetMTMNegative = MTMNegative × 0.35
```

The 0.35 netting factor represents a simplified application of close-out netting, typical for ISDA master agreements.

### 9.3 Potential future exposure (PFE)

```
PFE_{c,k,t} = (NetExposure_{c,k,t} + ReplacementCost_{c,k,t})
            × vol_annual_k
            × √(remaining_months_{c,k,t} / 12)
            × 1.65

where 1.65 ≈ 95th percentile of standard normal
```

Commodity annual volatilities:

| Commodity | Annual vol |
|---|---:|
| `crude_oil` | 35% |
| `lng` | 40% |
| `naphtha` | 38% |
| `natural_gas` | 45% |
| `diesel` | 32% |
| `power` | 55% |
| `chemicals` | 28% |
| `bunker_fuel` | 33% |

### 9.4 Wrong-way risk adjustment

For counterparties with `wrong_way_risk_flag = True`:
```
NetExposure_WWR = NetExposure × max(0.5, 75 / max(Brent_t, 10))
```

This multiplicatively amplifies exposure when oil prices fall — exactly the scenario where oil-producer creditworthiness also deteriorates.

---

## 10. AR ageing model (trade credit)

### 10.1 Bucket dynamics

```
AR_90plus_t  = AR_90plus_{t−1} × 0.85  +  AR_61_90_{t−1} × (1 − pay_61_90)
AR_61_90_t   = AR_31_60_{t−1} × (1 − pay_31_60)
AR_31_60_t   = AR_1_30_{t−1}  × (1 − pay_1_30)
AR_1_30_t    = new_AR_t × overdue_rate_t
AR_notdue_t  = new_AR_t × (1 − overdue_rate_t)

new_AR_t = approved_limit × delivery_rate × U(0.8, 1.2)
```

Tier-specific payment collection probabilities:

| Tier | Ratings | pay_1_30 range | pay_31_60 range | pay_61_90 range |
|---|---|---|---|---|
| Tier 1 (IG strong) | AAA–A- | 92–99% | 75–90% | 40–65% |
| Tier 2 (IG) | BBB+–BBB- | 78–92% | 55–75% | 25–50% |
| Tier 3 (sub-IG) | BB+–BB- | 55–78% | 30–55% | 10–30% |
| Tier 4 (high risk) | B and below | 35–60% | 10–35% | 3–15% |

### 10.2 Macro stress multiplier

```
overdue_rate_t = clip(base_overdue × macro_mult, 0.0, 0.70)

macro_mult = 1.0
           + 2.0 × max(0, (3.0 − GDP_t) / 3.0)
           + 1.5 × max(0, (BBBspread_t − 150) / 300)
```

---

## 11. Performance characteristics

### 11.1 Standard scale (4 000 borrowers, 120 months, 4 scenarios)

| Step | Time | Peak memory |
|---|---:|---:|
| Calendar + Macro + Borrowers + Facilities | < 10 s | < 200 MB |
| Financials (per scenario) | ~1 s | +30 MB |
| Operations (per scenario) | ~5 s | +60 MB |
| Reserves (per scenario) | ~2 s | +7 MB |
| Hedges (per scenario) | ~5 s | +13 MB |
| Trade credit (per scenario) | ~1 s | +15 MB |
| Trading exposure (per scenario) | ~1 s | +25 MB |
| Snapshots (per scenario) | ~5 s | +60 MB |
| Covenants (per scenario) | ~3 s | +50 MB |
| Ratings (per scenario) | ~45 s | +60 MB |
| Defaults (per scenario) | ~60 s | +10 MB |
| Recoveries (per scenario) | ~75 s | +10 MB |
| **Total per scenario** | **~200 s** | **< 350 MB** |
| **Total (4 scenarios + validation)** | **~620 s** | **< 500 MB** |

### 11.2 Bottleneck: defaults

The defaults generator iterates over triggered events in the ratings panel to enforce the 24-month resolution window. With 4 000 borrowers × 120 months = 480 000 panel rows, filtering and iterating triggered rows takes ~60 seconds per scenario.

If faster defaults generation is needed, this can be parallelised by scenario using Python's `multiprocessing.Pool`.

### 11.3 Bottleneck: ratings financial state refresh

For each of the 40 quarter boundaries, the ratings generator fetches financial state for all 4 000 borrowers from the `fin_sub` MultiIndex. This takes ~50 ms × 40 quarters = 2 s of lookup time. The remaining ~43 s per scenario is dominated by the time loop over 120 months and the `slices.append` / `pd.concat` at the end.

---

## 12. Data type conventions

| Data type | Used for | NumPy / pandas dtype |
|---|---|---|
| Monetary amounts (USD m) | Revenue, debt, exposure | `float64` |
| Ratios and fractions | Leverage, coverage, LGD | `float64` |
| Flags and booleans | `secured_flag`, `watchlist_flag` | `bool` |
| Integer counts | `dpd_days`, `spill_count`, stage | `int64` |
| Dates | All `as_of_*` columns | `datetime64[ns]` |
| Category IDs | `borrower_id`, `facility_id`, etc. | `object` (string) |
| Rating grades | `internal_grade`, `external_rating` | `object` (string) |

All monetary amounts are in **US dollars millions** (USD m) unless the column name specifies otherwise (e.g. `amount_usd` in `transaction_fact` is in raw USD).
