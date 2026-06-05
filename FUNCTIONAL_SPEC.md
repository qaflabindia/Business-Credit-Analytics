# Functional Specification — Credit Analytics (O&G Business AR)

**Document type:** Functional Specification
**Status:** Active
**Version:** 2.0
**Covers:** Synthetic AR dataset generation, use-case support, acceptance criteria

---

## 1. Purpose and scope

This document specifies what the Credit Analytics dataset generator produces, why it produces it, and what a correctly generated dataset must contain.

The generator produces a synthetic Oil & Gas commercial credit / AR dataset for the **business accounts-receivable function** of a Shell-like energy company. It is designed for four primary workflows:

1. **AR monitoring and ageing analysis** — understanding overdue concentration, bucket migration, and collection efficiency
2. **Credit limit management** — setting, reviewing, and optimising approved credit limits per customer
3. **Collections and credit-hold analytics** — building and validating credit-hold trigger models and risk mitigant strategies
4. **Stress testing** — measuring AR at risk and expected bad debt under adverse macro and commodity scenarios

The dataset is explicitly not intended for use in real credit decisions, regulatory reporting, or financial statements.

---

## 2. The AR credit function

The dataset models the **commercial trade-receivables book** of an O&G company:

- The company sells petroleum products, LNG, chemicals, and other goods to customers on credit
- Each customer has an approved credit limit and payment terms
- Delivered goods generate accounts receivable; the AR ages into overdue buckets if unpaid
- The credit function manages: limit setting, credit holds, blocked orders, and risk mitigants (LC, guarantee, insurance, collateral)

**Key risk questions this dataset answers:**
- How much does each customer owe, and how overdue is it?
- Which customers are deteriorating and should face a credit hold or reduced limit?
- How does the overdue rate change across macro scenarios?
- Are risk mitigants (LC, guarantee, insurance) adequately covering the riskiest customers?
- Which customer types carry the most commodity-correlated payment risk?

---

## 3. Use-case requirements

### UC-1: AR monitoring and ageing analysis

**Who uses it:** Commercial credit analysts, collections teams

**What the dataset must provide:**
- Monthly AR ageing buckets (not-due, 1–30, 31–60, 61–90, 90+ DPD) per customer
- Credit hold and blocked order flags with history
- Utilisation (AR / approved limit) over time

**Acceptance criteria:**
- AR bucket sums equal total AR (within 1% tolerance)
- Credit holds appear before or concurrent with 90+ DPD concentration, not after
- Overdue rates rise under stress scenarios relative to baseline

---

### UC-2: Credit limit management

**Who uses it:** Credit officers, commercial credit teams

**What the dataset must provide:**
- Approved and temporary credit limits per customer per month
- External ratings and credit tier assignments that drive limit calibration
- Payment terms appropriate to the credit tier

**Acceptance criteria:**
- Higher-tier customers (better rating) have higher approved limits on average
- Payment terms are within the allowed range (7–90 days) for all customers
- Temporary limit increases are present for ~5% of customer-months

---

### UC-3: Collections and credit-hold analytics

**Who uses it:** Collections teams, risk analytics

**What the dataset must provide:**
- Credit hold flags with clear overdue-rate triggers
- Blocked order flags for the most delinquent customers
- Risk mitigant flags (LC, guarantee, credit insurance, collateral) per customer
- Higher mitigant coverage for lower-quality (Tier 3/4) customers

**Acceptance criteria:**
- Customers on credit hold have materially higher overdue rates than those not on hold
- Blocked orders activated for customers with 90+ DPD bucket > 10% of limit
- Letter-of-credit frequency ≥ 60% for Tier 4 customers; ≤ 10% for Tier 1

---

### UC-4: Stress testing

**Who uses it:** Risk managers, treasury, financial planning teams

**What the dataset must provide:**
- Four clearly distinct macro scenarios with realistic commodity and economic shocks
- The same customer population across all scenarios (apples-to-apples comparison)
- Scenario-specific AR ageing so bad-debt exposure can be estimated per scenario

**Acceptance criteria:**
- Mean overdue rate in `severe_demand` > mean overdue rate in `baseline`
- Credit hold frequency in `severe_demand` > credit hold frequency in `baseline`
- Commodity-risk customers show more stress amplification than non-commodity-risk customers

---

## 4. Data completeness requirements

### 4.1 Time coverage

All AR rows must span the full simulation period with no unexplained gaps per active customer.

### 4.2 Customer type coverage (standard scale: 2 000 customers)

| Customer type | Expected count |
|---|---|
| `commodity_trader` | 280–320 |
| `corporate_buyer` | 340–380 |
| `utility` | 280–320 |
| `noc` | 180–220 |
| `independent_producer` | 240–270 |
| `refiner` | 220–250 |
| `petrochemical` | 180–220 |
| `shipping` | 120–150 |

### 4.3 Credit tier distribution

At the start of the simulation, the portfolio credit quality should broadly reflect an O&G commercial customer base:

| Tier | Rating band | Expected portfolio share |
|---|---|---|
| Tier 1 | AAA–A- | 15–25% |
| Tier 2 | BBB+–BBB- | 30–40% |
| Tier 3 | BB+–BB- | 25–35% |
| Tier 4 | B and below | 10–20% |

### 4.4 Risk mitigant coverage

| Mitigant | Expected prevalence |
|---|---|
| Letter of credit | Tier 4: ≥ 60%; Tier 1: ≤ 10% |
| Guarantee | Present for ≥ 5% of customers overall |
| Credit insurance | Present for ≥ 10% of customers overall |
| Collateral | Present for ≥ 5% of customers overall |

---

## 5. Data quality injection requirements

The generator must produce realistic imperfections:

| Imperfection | Required rate | Pattern |
|---|---|---|
| Late credit review dates (NaN) | ~4% of small customer rows | Customers with annual revenue < USD 100m |
| AR bucket rounding artefacts | ~8% of rows | Simulates manual entry / ERP rounding |
| Missing temporary limit records | ~3% of rows | Simulates system upload gaps |
| Duplicate month-end snapshots | ~0.03% of rows | Simulates double-posting |

---

## 6. Counterparty / customer requirements

### 6.1 Customer types

The `customer_dim` must include all 8 customer types. The customer master must include:
- At least one customer with `sanctions_flag = True`
- At least one customer with `kyc_status = flagged` or `pending`
- Both `commodity_risk_flag = True` and `False` cases across all types

### 6.2 AR book behaviour

The `trade_credit_terms_m` must exhibit:
- AR ageing concentration: 90+ DPD bucket grows during stress scenarios
- Credit holds activated for 5–25% of customers in any given stress month
- Blocked orders activated for 1–10% of customers in stress
- All four risk-mitigant flags present in meaningful proportions (not all-zero, not all-one)

---

## 7. Acceptance test checklist

A generated dataset passes acceptance if all of the following are true:

- [ ] 8/8 automated validation checks pass with no failures
- [ ] All 3 expected parquet files present in the output directory
- [ ] No parquet file has zero rows
- [ ] `scenario_id` takes exactly the expected values in `trade_credit_terms_m` and `macro_scenario_m`
- [ ] `customer_id` foreign keys in `trade_credit_terms_m` resolve to rows in `customer_dim`
- [ ] AR bucket sum = `current_ar_usd_m` within 1% tolerance for all rows
- [ ] All `payment_terms_days` in [7, 90]
- [ ] All `approved_credit_limit_usd_m` > 0
- [ ] `credit_hold_flag` customers have higher overdue rate than non-hold customers
- [ ] Mean overdue rate in `severe_demand` > mean overdue rate in `baseline`

---

## 8. Out of scope

| Out of scope | Why |
|---|---|
| Corporate lending / facilities / covenants | Lending book function — separate dataset |
| Commodity trading derivatives (MTM, PFE, CSA) | Trading book function — separate dataset |
| PD/LGD/ECL modelling inputs | The AR dataset does not include default event labels |
| Individual invoice-level AR | Dataset operates at customer-month aggregate level |
| Real company financial data | Fully synthetic dataset |
| Regulatory capital calculations | Not a regulatory submission |
| Non-energy sectors | Calibration is specific to O&G |
