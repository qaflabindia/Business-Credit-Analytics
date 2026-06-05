# Technical Specification — Credit Analytics (O&G Business AR)

**Document type:** Technical Specification
**Status:** Active
**Version:** 2.0
**Covers:** Mathematical models, generation algorithms, parameters

---

## 1. Reproducibility and random number generation

### 1.1 Seed architecture

```python
MASTER_SEED = 20260605

SEEDS = {
    "calendar":     20260606,   # date ranges
    "macro":        20260607,   # AR(1) macro paths
    "customers":    20260608,   # customer archetypes
    "trade_credit": 20260609,   # AR ageing simulation
    "dq_noise":     20260619,   # data quality injection
}
```

Each scenario receives a scenario-specific child seed offset:

```python
child_seed = SEEDS["trade_credit"] + hash(scenario_id) % 10_000
rng = np.random.default_rng(child_seed)
```

All RNG calls use NumPy's PCG64-based `default_rng`.

---

## 2. Macro scenario model

### 2.1 Correlated AR(1) process

Each macro variable follows a mean-reverting AR(1) process:

```
X_t = μ_t × (1 − ρ) + ρ × X_{t−1} + σ × ε_t
```

Innovations are correlated via Cholesky decomposition:

```
ε = Z × L^T    where Z ~ N(0, I) and Σ = L × L^T
```

### 2.2 Variable parameters

| Variable | Baseline (μ) | Persistence (ρ) | Monthly vol (σ) | Trend |
|---|---:|---:|---:|---|
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
| `carbon_price_usd_tco2` | 50.0 | 0.90 | 4.0 | +0.40/month |
| `usd_index` | 103.0 | 0.90 | 1.20 | — |
| `shipping_cost_index` | 100.0 | 0.80 | 8.0 | — |

### 2.3 Key pairwise correlations

| Variable A | Variable B | Correlation |
|---|---|---|
| `brent_usd_bbl` | `henry_hub_usd_mmbtu` | +0.40 |
| `brent_usd_bbl` | `ttf_usd_mmbtu` | +0.45 |
| `brent_usd_bbl` | `jkm_usd_mmbtu` | +0.50 |
| `ttf_usd_mmbtu` | `jkm_usd_mmbtu` | +0.70 |
| `brent_usd_bbl` | `global_gdp_yoy` | +0.35 |
| `global_gdp_yoy` | `us_gdp_yoy` | +0.80 |
| `us_gdp_yoy` | `unemployment_us` | −0.75 |
| `bbb_spread_bps` | `global_gdp_yoy` | −0.50 |
| `bbb_spread_bps` | `brent_usd_bbl` | −0.30 |
| `bbb_spread_bps` | `unemployment_us` | +0.60 |
| `brent_usd_bbl` | `shipping_cost_index` | +0.45 |
| `brent_usd_bbl` | `usd_index` | −0.35 |

### 2.4 Scenario overlays

Overlays are applied as additive or multiplicative shocks over specified month windows:

**`severe_demand`** (months 30–60):
- `global_gdp_yoy` −3.5 pp at peak
- `us_gdp_yoy` −4.6 pp at peak
- `brent_usd_bbl` ×0.65 at peak
- `bbb_spread_bps` +250 bps at peak

**`geopolitical_supply`** (months 45–72):
- `brent_usd_bbl` ×1.50 at peak
- `ttf_usd_mmbtu` ×1.70 at peak
- `jkm_usd_mmbtu` ×1.60 at peak
- `shipping_cost_index` ×1.80 at peak

**`disorderly_transition`** (months 60 onward):
- `brent_usd_bbl` ×0.80 at full ramp
- `carbon_price_usd_tco2` ×2.50 at full ramp

---

## 3. Customer generation model

### 3.1 Segment assignment

Customers are drawn by multinomial sampling from 8 segment types with specified shares. Within each segment, rating is drawn from a truncated normal distribution:

```
raw_idx ~ Normal(rating_mean_idx, rating_sigma)
rating_idx = clip(raw_idx, 0, 21)
external_rating = RATING_GRADES[rating_idx]
```

### 3.2 Segment parameters

| Segment | Share | Rating anchor (idx) | Rating sigma | Commodity risk prob |
|---|---:|---:|---:|---:|
| `commodity_trader` | 0.15 | 9 (BBB) | 4 | 0.45 |
| `corporate_buyer` | 0.18 | 11 (BB+) | 5 | 0.15 |
| `utility` | 0.15 | 7 (A-) | 3 | 0.25 |
| `noc` | 0.10 | 8 (BBB) | 5 | 0.70 |
| `independent_producer` | 0.13 | 11 (BB+) | 4 | 0.80 |
| `refiner` | 0.12 | 9 (BBB) | 4 | 0.35 |
| `petrochemical` | 0.10 | 9 (BBB) | 4 | 0.30 |
| `shipping` | 0.07 | 12 (BB) | 4 | 0.40 |

---

## 4. AR ageing model

### 4.1 Credit tier assignment

Each customer is assigned to a credit tier based on their external rating:

| Tier | Rating index range | Ratings |
|---|---|---|
| Tier 1 | 0–6 | AAA to A- |
| Tier 2 | 7–10 | BBB+ to BBB- |
| Tier 3 | 11–13 | BB+ to BB- |
| Tier 4 | 14–21 | B+ and below |

### 4.2 Credit limit initialisation

Approved limit is drawn uniformly within the tier range at the start:

```
approved_limit_i ~ Uniform(limit_lo_tier, limit_hi_tier)
```

Tier 1: [5, 50] USD m · Tier 2: [2, 20] · Tier 3: [0.5, 8] · Tier 4: [0.1, 3]

### 4.3 AR delivery and overdue induction

Each month, new AR is generated from deliveries:

```
new_ar_i,t = approved_limit_i × delivery_rate_i × U(0.8, 1.2)
new_ar_i,t = min(new_ar_i,t, approved_limit_i × 0.60)
```

Delivery rates by tier: Tier 1: [8%, 20%] · Tier 2: [10%, 25%] · Tier 3: [12%, 30%] · Tier 4: [15%, 40%]

The fraction of new AR that slips immediately to the 1–30 DPD bucket:

```
overdue_rate_i,t = base_overdue_i × effective_macro_mult_i,t
```

where:

```
effective_macro_mult_i,t = macro_mult_t + commodity_stress_t × 1[commodity_risk_i]

macro_mult_t = 1.0
             + 1.5 × max(0, (3.0 − GDP_yoy_t) / 3.0)
             + 1.0 × max(0, (BBBspread_t − 150) / 300)

commodity_stress_t = max(0, (75.0 − Brent_t) / 75.0)
```

Base overdue rates: Tier 1: 3% · Tier 2: 8% · Tier 3: 16% · Tier 4: 28%

### 4.4 Bucket aging (causal order each month)

```
ar_90+_t   = ar_90+_{t-1} × 0.85 + ar_61-90_{t-1} × (1 − p_61-90_i)
ar_61-90_t = ar_31-60_{t-1} × (1 − p_31-60_i)
ar_31-60_t = ar_1-30_{t-1}  × (1 − p_1-30_i)
ar_1-30_t  = new_ar × overdue_rate
ar_not-due_t = new_ar × (1 − overdue_rate)
```

Collection probabilities (resampled from tier ranges each month):

| Tier | p(collect 1–30) | p(collect 31–60) | p(collect 61–90) |
|---|---|---|---|
| Tier 1 | 0.92–0.99 | 0.75–0.90 | 0.40–0.65 |
| Tier 2 | 0.78–0.92 | 0.55–0.75 | 0.25–0.50 |
| Tier 3 | 0.55–0.78 | 0.30–0.55 | 0.10–0.30 |
| Tier 4 | 0.35–0.60 | 0.10–0.35 | 0.03–0.15 |

### 4.5 Credit hold and blocked order logic

```
credit_hold_i,t = True  if total_overdue_i,t / approved_limit_i > hold_threshold_i
                  (cured when falls below 50% of threshold)

blocked_order_i,t = True  if ar_90+_i,t / approved_limit_i > 0.10
```

Hold thresholds: Tier 1: 25% · Tier 2: 20% · Tier 3: 18% · Tier 4: 15%

### 4.6 Utilisation

```
utilisation_pct_i,t = clip(total_ar_i,t / approved_limit_i × 100, 0, 200)
```

---

## 5. Noise injection model

Four types of AR data imperfection are injected into the baseline slice:

| Type | Mechanism | Rate |
|---|---|---|
| Late review dates | `next_review_due_date` set to NaT | 4% of small customers (revenue < USD 100m) |
| AR rounding | Overdue bucket values rounded to nearest $1 000 | 8% of rows |
| Missing temp limits | `temporary_credit_limit_usd_m` set to NaN | 3% of rows |
| Duplicate rows | Full row duplicated | 0.03% of rows |

---

## 6. Validation model

Eight automated checks run after baseline generation:

| Check | Test | Pass condition |
|---|---|---|
| `bucket_consistency` | `|bucket_sum − current_ar| / current_ar` | Mean error < 1% |
| `credit_limits_positive` | `approved_credit_limit_usd_m > 0` | < 0.1% violations |
| `credit_limits_bounded` | `approved_credit_limit_usd_m ≤ 1000` | < 0.1% violations |
| `utilisation_distribution` | `current_ar > 0` | Zero-AR rows < 20% |
| `utilisation_cap` | `utilisation_pct ≤ 150` | > 150% rows < 5% |
| `hold_overdue_correlation` | `mean_overdue(hold=True) > mean_overdue(hold=False)` | Must hold |
| `commodity_risk_check` | `mean_overdue(risk=True) ≥ mean_overdue(risk=False)` | Must hold |
| `payment_terms_range` | `7 ≤ payment_terms_days ≤ 90` | < 0.1% violations |

---

## 7. Performance characteristics

| Scale | Customers | Months | Scenarios | Wall time | Peak memory | Output size |
|---|---:|---:|---|---:|---:|---:|
| `lite` | 500 | 36 | 2 | < 5 s | < 100 MB | ~2 MB |
| `standard` | 2 000 | 120 | 4 | ~30 s | < 200 MB | ~25 MB |
| `research` | 8 000 | 180 | 4 | ~5 min | ~400 MB | ~350 MB |
