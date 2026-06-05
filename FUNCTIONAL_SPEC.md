# Functional Specification — Credit Analytics

**Document type:** Functional Specification
**Status:** Active
**Version:** 1.0
**Covers:** Synthetic dataset generation, use-case support, acceptance criteria

---

## 1. Purpose and scope

This document specifies what the Credit Analytics dataset generator does, why it does it, and what a correctly generated dataset must contain.

The generator produces a synthetic oil and gas credit portfolio dataset calibrated to a Shell-like integrated supermajor archetype. It is designed for use in four primary credit analytics workflows:

1. **Credit scoring** — building and validating models that assign an internal credit grade to a borrower
2. **PD and LGD modelling** — estimating the probability of default and the loss given default, for regulatory (IRB) and IFRS 9 purposes
3. **Stress testing** — assessing how portfolio credit losses change under adverse macro and commodity scenarios
4. **Portfolio monitoring** — building surveillance tools that detect early warning signals and track exposure concentrations

The dataset is explicitly not intended to replace real observed credit data for regulatory capital calculations, financial reporting, or actual lending decisions.

---

## 2. Three credit books

A complete Shell-like credit dataset must cover three distinct credit relationships:

### 2.1 Corporate lending / facilities book

Shell extends credit facilities to oil and gas companies:
- Reserve-Based Lending (RBL) to upstream producers
- Revolving credit facilities and term loans to all segments
- Bonds held as investments

**Key risk questions this book answers:**
- Is the borrower's leverage and cash flow adequate to service debt?
- Is the collateral (reserves or assets) sufficient to recover the loan if the borrower defaults?
- Are financial covenants being met, and if not, what is Shell's remediation strategy?
- What is the expected credit loss (PD × LGD × EAD) at borrower and portfolio level?

### 2.2 Commercial trade receivables book

Shell sells petroleum products, LNG, chemicals, and other goods on credit to commercial customers:

**Key risk questions this book answers:**
- How much does each customer owe Shell, and how overdue is it?
- Is the customer's credit limit appropriate given their financial condition?
- Should Shell impose a credit hold or blocked orders on a deteriorating customer?
- Are risk mitigants (LC, guarantee, insurance, collateral) adequate?

### 2.3 Commodity trading counterparty book

Shell trades oil, gas, LNG, refined products, and derivatives with commodity trading counterparties:

**Key risk questions this book answers:**
- What is the current mark-to-market exposure to each counterparty?
- What is the potential future exposure (PFE) if prices move further?
- Are netting and CSA agreements reducing the gross exposure adequately?
- Is wrong-way risk present — i.e. does this counterparty's creditworthiness deteriorate exactly when Shell's exposure to them is largest?

---

## 3. Use-case requirements

### UC-1: Credit scoring and annual review

**Who uses it:** Credit officers, relationship managers

**What the dataset must provide:**
- One row per borrower per quarter with financial ratios (leverage, coverage, liquidity, cash flow)
- Monthly rating history showing grade progression and warning signals
- Operational data (production, reserves, hedge coverage) for upstream borrowers
- A ground-truth default label to validate model discriminatory power

**Acceptance criteria:**
- Leverage ratio (`net_debt_ebitda_x`) correlates positively with default rates at segment level
- Interest coverage (`interest_coverage_x`) correlates negatively with default rates
- Rating grades are monotonically ordered by default frequency (Spearman ρ > 0.80)
- Internal PD covers the full range from < 0.01% (AAA equivalents) to > 40% (near-distressed)

---

### UC-2: PD and LGD modelling

**Who uses it:** Quants, model developers, model validators

**What the dataset must provide:**
- Monthly through-the-cycle (TTC) and point-in-time (PIT) PD paths per borrower
- Clearly labelled default events with Basel-definition triggers (90 DPD, UTP, bankruptcy, restructuring)
- Recovery cash flows with timing, costs, and final LGD per defaulted facility
- Enough defaults to be statistically useful: at least 200 unique default events in the standard scale baseline scenario

**Acceptance criteria:**
- Mean LGD is between 0.10 and 0.80 across all defaulted facilities
- Secured facility LGD is lower than unsecured facility LGD (seniority ordering preserved)
- PD–LGD positive dependence is present: mean LGD is higher in the severe_demand scenario than in baseline
- No "time leakage" — no variable for period t uses information first available after t
- PD in stress scenarios is materially higher than in baseline (stress amplification > 1.5×)

---

### UC-3: Stress testing

**Who uses it:** Risk managers, capital planning teams, regulatory teams

**What the dataset must provide:**
- Four clearly distinct macro scenarios with realistic shocks
- The same borrower population across all scenarios, allowing apples-to-apples comparison
- Scenario-specific PD, LGD, and EAD so portfolio expected loss can be computed per scenario
- Covenant breach frequencies that rise in stress scenarios
- IFRS 9 stage migration that shows movement from Stage 1 → 2 → 3 under stress

**Acceptance criteria:**
- Portfolio expected loss under `severe_demand` ≥ 2× portfolio expected loss under `baseline`
- Default event count in `severe_demand` ≥ 1.5× default event count in `baseline`
- Mean portfolio LGD in `severe_demand` ≥ mean portfolio LGD in `baseline`
- Covenant breach rate in `severe_demand` > covenant breach rate in `baseline`

---

### UC-4: Portfolio monitoring and early warning

**Who uses it:** Credit surveillance teams, watchlist managers

**What the dataset must provide:**
- Monthly watchlist flags, DPD counts, and IFRS 9 stage assignments
- Covenant test results showing headroom and breach history
- Rating migration paths showing downgrade velocity
- AR ageing and credit holds in the trade book
- Limit breach flags in the trading book
- Counterparty-level wrong-way risk and netting agreement status

**Acceptance criteria:**
- Watchlist flag appears before default in the time series (leading indicator property)
- Covenant breaches are more frequent for borrowers that eventually default
- Credit holds in the trade book increase under stress scenarios
- Limit breaches in the trading book respond to commodity price shocks

---

## 4. Data completeness requirements

### 4.1 Time coverage

| Table | Required coverage | Notes |
|---|---|---|
| All time-series tables | Full period from start to last month | No unexplained gaps |
| `reserves_q` | Upstream borrowers only | Non-upstream borrowers have no rows here (not NaN rows) |
| `borrower_operations_m` | Production columns NaN for non-upstream | Not zero — NaN signals "not applicable" |
| `recovery_cashflow_fact` | Resolution period only | Starts 1 month after default date; no rows before default |

### 4.2 Segment coverage

| Segment | Required count (standard scale) | Notes |
|---|---|---|
| `supermajor` | 15–25 | Shell-like companies |
| `large_integrated` | 120–160 | |
| `independent_upstream` | 1 200–1 400 | Largest segment by count |
| `midstream_lng` | 420–500 | |
| `refining_marketing` | 360–440 | |
| `oilfield_services` | 850–1 000 | |
| `trading_petrochemicals` | 680–800 | |

### 4.3 Default sample requirements

| Requirement | Minimum | Target |
|---|---|---|
| Unique defaulted borrowers — baseline | 100 | 250–400 |
| Unique defaulted borrowers — severe_demand | 200 | 500–800 |
| Default types present | All 4 types | dpd_90, utp, bankruptcy, distressed_restructuring |
| Facilities with recovery rows | ≥ 80% of defaulted facilities | |

### 4.4 Rating distribution requirements

At each point in time, the portfolio-wide rating distribution should broadly match investment-grade-heavy oil and gas portfolios:

| Rating band | Expected portfolio share |
|---|---|
| AAA to A- | 20–35% |
| BBB+ to BBB- | 25–35% |
| BB+ to BB- | 20–30% |
| B and below | 5–15% |
| CCC and below | < 5% |

---

## 5. Data quality injection requirements

The generator must produce a dataset that is realistic in its imperfections, not artificially clean. The following imperfections must be present in the baseline tables:

| Imperfection | Required rate |
|---|---|
| Late financial filings (NaN in financial columns for private names) | 3–8% of private borrower quarters |
| Reserve report delays | 5–10% of upstream quarter-ends |
| Partial hedge disclosure (NaN in floor/cap for smaller private names) | 10–20% of qualifying rows |
| Unit conversion suspects in production data | 0.1–0.3% of rows |
| Restatement flags in financial history | 1–3% of borrower histories |
| Stale external ratings for unlisted borrowers | 2–5% of unlisted months |
| Collateral valuation noise | 5–10% relative variation |
| Duplicate transactions | ~0.05% of transaction rows |

Missingness must be **structural, not random**: missing data must be more frequent for private borrowers than public ones, and for smaller borrowers than larger ones.

---

## 6. Counterparty and trading book requirements

### 6.1 Counterparty types

The `counterparty_dim` must include at least 8 of the 10 counterparty types defined in the specification. The trading book counterparties must include:
- At least one counterparty with `wrong_way_risk_flag = True` in each commodity category
- At least one counterparty with `sanctions_flag = True`
- At least one counterparty with `kyc_status = flagged` or `pending`
- Both `netting_agreement_flag` True and False cases

### 6.2 Trade credit book

The `trade_credit_terms_m` must exhibit:
- AR ageing concentration: 90+ DPD bucket grows during stress scenarios
- Credit holds activated for 5–20% of customers in any given stress month
- Blocked orders activated for 2–10% of customers in stress
- All four risk-mitigant flags (`letter_of_credit_flag`, `guarantee_flag`, `credit_insurance_flag`, `collateral_required_flag`) present in meaningful proportions

### 6.3 Trading exposure book

The `trading_exposure_m` must exhibit:
- Net exposure after netting materially lower than gross for counterparties with `netting_agreement_flag = True`
- Margin calls activated when `mtm_negative_usd_m` exceeds the threshold for CSA counterparties
- PFE > net_exposure in all rows (PFE represents a peak, not current exposure)
- Limit breaches of 3–12% across the trading book in any given month

---

## 7. Acceptance test checklist

A generated dataset passes acceptance if all of the following are true:

- [ ] 11/11 automated validation checks pass with no failures
- [ ] All 17 expected parquet files are present in the output directory
- [ ] No parquet file has zero rows
- [ ] `scenario_id` takes exactly the expected values in every time-series table
- [ ] `borrower_id` foreign keys in all tables resolve to rows in `borrower_dim`
- [ ] `facility_id` foreign keys in all tables resolve to rows in `facility_dim`
- [ ] `counterparty_id` foreign keys in trade/trading tables resolve to `counterparty_dim`
- [ ] `default_id` in `recovery_cashflow_fact` resolves to `default_event_fact`
- [ ] `reserve_life_years` is in [0.5, 30] for all upstream borrowers
- [ ] PDP + PDNP + PUD ≤ proved reserves (within 1% tolerance)
- [ ] Mean LGD is between 0.10 and 0.80 for all scenarios
- [ ] Secured facility LGD < unsecured facility LGD
- [ ] Severe demand scenario defaults > baseline scenario defaults
- [ ] No future leakage: no `as_of_month` or `as_of_quarter` is later than the simulation end date

---

## 8. Out of scope

The following are explicitly not in scope for this dataset:

| Out of scope | Why |
|---|---|
| Real company financial data | This is a fully synthetic dataset |
| IFRS 9 ECL calculation engine | The dataset provides inputs; an ECL calculator is a separate model |
| Regulatory capital calculations | The dataset supports model building; it is not a regulatory submission |
| Real-time or streaming data | The dataset is a static batch generation; streaming is a separate architecture |
| Non-energy sectors | The calibration is specific to oil and gas; other sectors are not modelled |
| Single-name credit derivatives (CDS) | Only cash and physical exposure is modelled |
| Insurance or surety product pricing | Outside scope |
| Environmental liability valuation | Decommissioning provision is modelled; broader environmental liability is not |
