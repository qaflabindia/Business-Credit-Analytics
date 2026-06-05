# Credit Analytics — Data Dictionary

**Dataset:** Synthetic Oil & Gas Credit Portfolio (Shell-like Integrated Supermajor Archetype)
**Scale:** Standard — 4 000 borrowers · 2 000 counterparties · 120 months · 4 scenarios
**Format:** Parquet files in `data_out/`
**Total size:** ~443 MB · 17 tables

---

## What this dataset models

Shell's credit function has three distinct books:

| Book | What it covers | Tables |
|---|---|---|
| **Lending book** | Companies Shell has given loans or credit facilities to | `borrower_dim`, `facility_dim`, `covenant_def_dim`, `facility_snapshot_m`, `covenant_test_fact`, `default_event_fact`, `recovery_cashflow_fact` |
| **Commercial / trade receivables book** | Companies Shell sells products to (and who owe Shell money) | `counterparty_dim`, `trade_credit_terms_m` |
| **Commodity trading book** | Companies Shell trades oil, gas, and derivatives with | `counterparty_dim`, `trading_exposure_m` |

Supporting tables that cut across all three books:

`borrower_financials_q` · `borrower_operations_m` · `reserves_q` · `hedge_position_m` · `rating_history_m` · `macro_scenario_m` · `transaction_fact`

---

## The four scenarios

Every time-series table carries a `scenario_id` column. That column takes one of four values:

| Scenario | What it represents | Key shock |
|---|---|---|
| `baseline` | Normal operating environment | Brent ~$75, GDP growth ~3%, spreads normal |
| `severe_demand` | Global recession (like the 2008–2009 financial crisis or a hard-landing) | GDP falls 4.6%, Brent drops 35%, credit spreads spike |
| `geopolitical_supply` | Middle East or Russia supply disruption | Brent spikes 50%, gas prices spike 70%, shipping costs double |
| `disorderly_transition` | Abrupt energy-transition repricing | Carbon price triples, long-run oil demand collapses, Brent falls 20% |

---

## Table overview

| Table name | Rows (standard) | One row = | Updated |
|---|---:|---|---|
| `borrower_dim` | 4,000 | One oil & gas company Shell lends to | Static (set once) |
| `counterparty_dim` | 2,000 | One company Shell trades with or sells to | Static |
| `facility_dim` | 10,415 | One loan or credit line extended to a borrower | Static |
| `covenant_def_dim` | 26,129 | One financial condition attached to a facility | Static |
| `macro_scenario_m` | 480 | One month × one scenario of market conditions | Monthly |
| `borrower_financials_q` | 640,000 | One borrower's financial results for one quarter × one scenario | Quarterly |
| `borrower_operations_m` | 1,920,000 | One borrower's production/operational data for one month × scenario | Monthly |
| `reserves_q` | 234,080 | One upstream borrower's oil & gas reserve position for one quarter | Quarterly |
| `hedge_position_m` | 462,974 | One hedging contract's value for one month | Monthly |
| `facility_snapshot_m` | 1,830,220 | One loan's exposure and status for one month × scenario | Monthly |
| `covenant_test_fact` | 1,526,004 | One financial-condition test result on one date | Quarterly |
| `rating_history_m` | 1,920,000 | One borrower's credit rating for one month × scenario | Monthly |
| `default_event_fact` | 15,367 | One default event on one facility | Event-level |
| `recovery_cashflow_fact` | 274,559 | One monthly cash recovery after a default | Monthly |
| `trade_credit_terms_m` | 656,160 | One commercial customer's receivables position for one month | Monthly |
| `trading_exposure_m` | 1,006,560 | One counterparty's exposure in one commodity for one month | Monthly |
| `transaction_fact` | 45,777 | One financial transaction (drawdown, repayment, fee) | Event-level |

---

## Dimension and reference tables

### `borrower_dim` — The companies Shell has lent money to

One row per borrower. These are oil & gas companies across 7 segment types.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `borrower_id` | Borrower code | Unique identifier for this company | `BRW000042` |
| `segment` | Business type | Which part of the oil & gas industry this company is in | `independent_upstream` |
| `country` | Country | Where the company is headquartered | `US`, `NO`, `SA` |
| `region` | World region | Broader geographic grouping | `North_America` |
| `ownership_type` | Who owns it | Whether the company is publicly listed, state-owned, or private | `public`, `soe`, `private` |
| `listed_flag` | Publicly listed? | `True` if the company's shares trade on a stock exchange | `True` |
| `fiscal_year_end_month` | Year-end month | Which month the company's financial year ends (affects when results are published) | `12` (December) |
| `shell_like_flag` | Major integrated? | `True` for the largest integrated companies similar to Shell itself | `False` |
| `has_reserves` | Has oil reserves? | `True` for companies that own oil or gas in the ground | `True` |
| `revenue_init_usd_m` | Starting revenue (USD m) | Annual revenue at the start of the simulation, in millions of US dollars | `4 200.0` |
| `ebitda_margin_init` | Starting profit margin | Earnings before interest, tax, depreciation and amortisation as a fraction of revenue | `0.42` (42%) |
| `leverage_init` | Starting debt level | Net debt divided by annual EBITDA — a measure of how indebted the company is. Above 4× is considered stretched. | `2.8` |
| `hedge_ratio` | Commodity hedging level | What fraction of the next 12 months of production the company has locked in at a fixed price | `0.48` (48%) |
| `offshore_share` | Offshore fraction | Fraction of production that comes from offshore fields (which are more expensive to decommission) | `0.20` |
| `mature_asset_share` | Mature field fraction | Fraction of assets that are in older, declining fields (relevant for decommissioning costs) | `0.55` |
| `decomm_prov_undisc_init_usd_m` | Decommissioning liability (USD m) | The undiscounted cost of plugging and abandoning wells and removing platforms at end of field life | `850.0` |
| `reserve_life_init` | Reserve life (years) | How many years of production the company's proved reserves can sustain at current output rates | `7.2` |
| `beta_oil` | Oil price sensitivity | How much this company's revenue changes for a 1% change in the oil price. Higher = more exposed. | `0.70` |
| `beta_gas` | Gas price sensitivity | Same concept for natural gas prices | `0.30` |
| `beta_gdp` | Economic sensitivity | How much the company's revenue is tied to overall economic growth | `0.03` |
| `beta_commodity` | Overall commodity sensitivity | Combined measure of how commodity-price-sensitive this company is (used in the credit model) | `0.65` |
| `alpha_pd` | Base default risk level | Starting point in the default probability calculation — lower (more negative) means less risky | `-3.2` |
| `mu_revenue` | Revenue growth trend | Expected quarterly growth rate in revenues, before commodity price effects | `0.005` |

**Segment reference:**

| Segment value | Plain English |
|---|---|
| `supermajor` | Shell, BP, ExxonMobil, TotalEnergies scale companies |
| `large_integrated` | Large but not supermajor — e.g. regional integrated players |
| `independent_upstream` | Companies that only explore and produce oil & gas |
| `midstream_lng` | Pipeline operators, LNG terminals, gas processors |
| `refining_marketing` | Refineries and petrol station networks |
| `oilfield_services` | Drilling companies, well services, equipment suppliers |
| `trading_petrochemicals` | Oil traders and chemical producers |

---

### `counterparty_dim` — Companies Shell trades with or sells to

One row per counterparty. Distinct from borrowers — these are the commercial and trading credit relationships.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `counterparty_id` | Counterparty code | Unique identifier | `CPT000318` |
| `counterparty_type` | Type of counterparty | What kind of company this is in the context of Shell's trading | `commodity_trader` |
| `sector` | Industry sector | Broad industry classification | `energy_trading` |
| `country` | Country | Where the counterparty is based | `SG`, `AE`, `GB` |
| `region` | World region | Geographic grouping | `Asia_Pacific` |
| `external_rating` | Credit rating | The credit agency's opinion of how likely this counterparty is to pay its debts | `BBB`, `BB+` |
| `wrong_way_risk_flag` | Wrong-way risk | `True` if this counterparty's creditworthiness tends to get worse at exactly the same time as Shell's exposure to them increases — e.g. an oil producer whose revenues fall when oil prices fall, but Shell is owed more money from them at low prices | `True` |
| `connected_party_flag` | Related party | `True` if this counterparty has ownership or management connections to Shell — requires extra scrutiny | `False` |
| `netting_agreement_flag` | Netting agreement in place | `True` if Shell and this counterparty have a legal agreement to offset what they owe each other, reducing net exposure | `True` |
| `csa_flag` | Collateral agreement | `True` if there is a Credit Support Annex — meaning the losing party must post cash or securities as collateral when losses build up | `True` |
| `kyc_status` | KYC check result | Know-Your-Customer review outcome: is the counterparty cleared to do business with Shell? | `approved`, `pending`, `flagged` |
| `sanctions_flag` | Sanctions risk | `True` if the counterparty is on or associated with a sanctions list | `False` |
| `credit_book` | Which credit book | Whether this counterparty appears in the trading book, commercial trade book, or both | `trading`, `trade`, `both` |
| `annual_revenue_est_usd_m` | Estimated annual revenue (USD m) | Shell's estimate of the counterparty's total annual revenues — used to size credit limits | `620.0` |

**Counterparty type reference:**

| Type | Who they are | Typical exposure |
|---|---|---|
| `bank` | Financial institution — counterparty on derivatives and settlements | Trading book |
| `commodity_trader` | Vitol, Trafigura, Glencore-type commodity houses | Trading book |
| `noc` | National Oil Company — Saudi Aramco, ADNOC, NIOC | Both books |
| `independent_producer` | E&P company that buys/sells crude from Shell | Both books |
| `refiner` | Buys crude from Shell to process into products | Trade book |
| `utility` | Power or gas company that buys LNG or gas from Shell | Trade book |
| `petrochemical` | Buys naphtha or chemicals from Shell | Trade book |
| `shipping` | Pays Shell for bunker fuel; voyage charter partners | Trade book |
| `sovereign` | Government entity or sovereign wealth fund | Trading book |
| `corporate_buyer` | Industrial company buying diesel, gas, lubricants | Trade book |

---

### `facility_dim` — The loans and credit lines Shell has extended

One row per credit facility. A borrower can have several facilities of different types.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `facility_id` | Facility code | Unique identifier for this loan or credit line | `FAC0012847` |
| `borrower_id` | Borrower | Which company this facility belongs to | `BRW000042` |
| `facility_type` | Loan type | What kind of credit product this is (see table below) | `RBL` |
| `currency` | Currency | Currency the facility is denominated in | `USD` |
| `secured_flag` | Is it secured? | `True` if Shell holds an asset (collateral) that it can take if the borrower defaults | `True` |
| `seniority` | Priority in a default | If the borrower goes bust, in what order does Shell get paid? Senior secured = first in line. | `senior_secured` |
| `origination_date` | Date opened | When this facility was first put in place | `2018-03-31` |
| `maturity_date` | Expiry date | When the facility must be fully repaid | `2025-03-31` |
| `commitment_usd_m` | Total credit limit (USD m) | The maximum amount the borrower is allowed to draw. Similar to a credit card limit. | `350.0` |
| `spread_bps` | Interest margin (basis points) | The extra interest Shell charges above the benchmark rate, in hundredths of a percent. 200 bps = 2% above the base rate. | `225` |
| `rate_type` | Fixed or floating rate | `floating` means the interest rate moves with the market; `fixed` is locked in at origination | `floating` |
| `benchmark` | Interest rate reference | The market rate the floating spread is added on top of | `SOFR` |
| `collateral_type` | What backs the loan | What asset Shell can sell if the borrower fails to repay | `proved_reserves` |
| `borrowing_base_flag` | Borrowing base facility | `True` for Reserve-Based Lending — the amount the borrower can draw is linked to the value of their oil reserves, not just a fixed limit | `True` |
| `guarantor_id` | Guarantor | If a parent company or third party has guaranteed this loan, their ID goes here | `null` |

**Facility type reference:**

| Type | Plain English | Who uses it |
|---|---|---|
| `RBL` | Reserve-Based Lending — the credit limit is based on the value of proved oil and gas reserves; revised every 6 months | Upstream oil & gas producers |
| `RCF` | Revolving Credit Facility — like a company credit card: draw, repay, draw again up to the limit | All segments |
| `term_loan` | Term Loan — a fixed sum lent for a fixed period; repaid on a schedule | All segments |
| `bond` | Corporate Bond — Shell buys the company's debt securities; typically at a fixed coupon | Larger companies |
| `trade_finance` | Trade Finance — short-term credit secured against commodity shipments or receivables | Trading & refining companies |

---

### `covenant_def_dim` — The financial conditions attached to each loan

One row per covenant (financial condition). Each facility typically has 2–4 covenants.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `covenant_id` | Covenant code | Unique identifier | `COV00048371` |
| `facility_id` | Which facility | The loan this condition applies to | `FAC0012847` |
| `test_name` | Test name | Short label for this financial test | `net_debt_ebitda` |
| `test_formula` | How it's calculated | The accounting formula used to calculate the ratio being tested | `net_debt / ebitda_ltm` |
| `threshold_operator` | Pass/fail direction | Whether the value must be below (`<=`) or above (`>=`) the threshold to pass | `<=` |
| `threshold_value` | The limit | The specific number the borrower must stay within | `3.5` |
| `frequency` | How often tested | How often the borrower must prove they are within the limit | `quarterly` |
| `cure_days` | Days to fix a breach | How many days the borrower has to fix a covenant breach before it becomes an event of default | `30` |
| `waiver_allowed_flag` | Can it be waived? | `True` if Shell can agree to waive a breach rather than calling a default | `True` |

**Covenant type reference:**

| `test_name` | Plain English | A breach means… |
|---|---|---|
| `net_debt_ebitda` | Leverage ratio | The borrower's debt is more than N× their annual profit — they are over-borrowed |
| `ebitda_interest` | Interest cover | The borrower's profit is too thin to comfortably service their interest bill |
| `drawn_vs_borrowing_base` | Borrowing base deficiency | The borrower has drawn more than their oil reserves are worth — they must repay the excess |
| `minimum_liquidity` | Liquidity test | The borrower does not have enough cash to cover upcoming debt payments |

---

## Market and macro reference

### `macro_scenario_m` — The market environment each month

One row per month × scenario. This is the economic backdrop that drives all borrower outcomes.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `as_of_month` | Month end date | The last day of the month this row describes | `2022-03-31` |
| `scenario_id` | Scenario | Which of the four economic scenarios this row belongs to | `severe_demand` |
| `brent_usd_bbl` | Brent crude price ($/bbl) | The global oil benchmark price in US dollars per barrel | `52.40` |
| `henry_hub_usd_mmbtu` | US gas price ($/MMBtu) | US natural gas price at the Henry Hub delivery point | `3.20` |
| `ttf_usd_mmbtu` | European gas price ($/MMBtu) | European natural gas price at the TTF hub (Netherlands) | `8.50` |
| `jkm_usd_mmbtu` | Asian LNG price ($/MMBtu) | Japan-Korea marker price for LNG — the key Asian gas benchmark | `10.20` |
| `global_gdp_yoy` | Global GDP growth (% pa) | Year-on-year change in global economic output | `1.80` |
| `us_gdp_yoy` | US GDP growth (% pa) | US economic growth rate | `-1.20` |
| `eu_gdp_yoy` | EU GDP growth (% pa) | European economic growth rate | `-0.80` |
| `uk_gdp_yoy` | UK GDP growth (% pa) | UK economic growth rate | `-1.00` |
| `unemployment_us` | US unemployment rate (%) | Percentage of the US workforce without a job | `8.40` |
| `bbb_spread_bps` | BBB credit spread (bps) | The extra yield (in hundredths of a percent) investors demand above government bonds to hold BBB-rated corporate bonds. A measure of market stress — widens in recessions. | `320` |
| `policy_rate_bps` | Central bank rate (bps) | The US Federal Reserve's benchmark interest rate | `150` |
| `carbon_price_usd_tco2` | Carbon price ($/tonne CO₂) | The cost to emit one tonne of CO₂, relevant for transition risk | `125.0` |
| `usd_index` | US dollar strength | Index measuring the dollar against a basket of currencies. Above 100 = strong dollar. | `109.5` |
| `shipping_cost_index` | Shipping cost index | Relative cost of moving cargo by sea (100 = baseline level) | `185.0` |

---

## Borrower time-series tables

### `borrower_financials_q` — Quarterly financial results

One row per borrower × quarter × scenario. This is the equivalent of a company's published quarterly earnings report.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `borrower_id` | Borrower | Which company | `BRW000042` |
| `as_of_quarter` | Quarter end date | The last day of the quarter (March, June, September, December) | `2022-03-31` |
| `scenario_id` | Scenario | Which economic scenario | `baseline` |
| `revenue_usd_m` | Revenue (USD m) | Total sales income in the quarter, in millions of US dollars | `1 050.0` |
| `ebitda_usd_m` | Operating profit (USD m) | Earnings Before Interest, Tax, Depreciation and Amortisation — the core operating profit before financing costs | `472.0` |
| `ebit_usd_m` | EBIT (USD m) | Operating profit after deducting depreciation (the accounting wear-and-tear on assets) | `346.0` |
| `cfo_usd_m` | Cash from operations (USD m) | Actual cash generated by the business — more reliable than accounting profit for credit purposes | `395.0` |
| `capex_usd_m` | Capital expenditure (USD m) | Cash spent on drilling new wells, building plant, or buying equipment | `220.0` |
| `interest_expense_usd_m` | Interest paid (USD m) | Cash cost of servicing the company's borrowings | `38.0` |
| `tax_paid_usd_m` | Tax paid (USD m) | Cash taxes paid to governments | `68.0` |
| `cash_usd_m` | Cash held (USD m) | Liquid cash and short-term investments on the balance sheet | `185.0` |
| `gross_debt_usd_m` | Total borrowings (USD m) | All interest-bearing debt: bank loans, bonds, revolving credit | `1 420.0` |
| `net_debt_usd_m` | Net debt (USD m) | Total borrowings minus cash held. Negative means the company holds more cash than it owes. | `1 235.0` |
| `total_assets_usd_m` | Total assets (USD m) | Everything the company owns: fields, refineries, plant, receivables, cash | `4 800.0` |
| `total_equity_usd_m` | Shareholders' equity (USD m) | The residual value belonging to shareholders: assets minus all liabilities | `2 180.0` |
| `working_capital_usd_m` | Working capital (USD m) | Short-term assets minus short-term liabilities — a measure of short-term financial health | `92.0` |
| `receivables_usd_m` | Trade receivables (USD m) | Money owed to the company by customers who have not yet paid | `63.0` |
| `inventory_usd_m` | Inventory (USD m) | Value of oil, gas, and products held in storage, tankers, or pipelines | `42.0` |
| `decommissioning_prov_disc_usd_m` | Decommissioning liability — discounted (USD m) | The present value of the future cost of plugging wells, removing platforms, and restoring sites. The discounted figure is what appears on the balance sheet. | `820.0` |
| `decommissioning_prov_undisc_usd_m` | Decommissioning liability — undiscounted (USD m) | The same future cost in today's dollars without discounting — larger than the discounted figure; used for engineering estimates | `1 480.0` |
| `leases_usd_m` | Lease liabilities (USD m) | Debt-like obligations from long-term leases (rigs, vessels, office space) — treated as debt under IFRS 16 | `58.0` |
| `net_debt_ebitda_x` | Leverage ratio (×) | Net debt divided by annualised EBITDA. The most commonly tested covenant ratio. Above 4× is typically stretched; above 6× is distressed. | `2.6` |
| `interest_coverage_x` | Interest cover (×) | Annualised EBITDA divided by annualised interest expense. How many times over does the company cover its interest bill? Below 2× is a warning sign. | `12.4` |
| `cash_ratio` | Cash-to-debt ratio | Cash on hand divided by total gross debt. Below 0.05 (5%) means the company has very little liquid buffer. | `0.13` |

---

### `borrower_operations_m` — Monthly production and operational data

One row per borrower × month × scenario. Only upstream (oil-producing) borrowers have meaningful production data; other segments have NaN in production columns.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `borrower_id` | Borrower | Which company | `BRW000042` |
| `as_of_month` | Month | The month this data refers to | `2022-03-31` |
| `scenario_id` | Scenario | Which economic scenario | `baseline` |
| `liq_prod_kboed` | Oil & liquids production (kboe/d) | Crude oil and liquid production in thousands of barrels of oil equivalent per day | `28.4` |
| `gas_prod_mmscfd` | Gas production (MMscf/d) | Natural gas production in millions of standard cubic feet per day | `62.0` |
| `total_prod_kboed` | Total production (kboe/d) | Oil and gas production combined, all converted to equivalent oil barrels per day | `39.5` |
| `realised_oil_price_usd_bbl` | Realised oil price ($/bbl) | The actual average price this company received for its oil — slightly different from Brent due to quality differentials and location | `72.80` |
| `realised_gas_price_usd_mmbtu` | Realised gas price ($/MMBtu) | The actual average price received for gas — varies by regional market and contract type | `3.40` |
| `refining_margin_usd_bbl` | Refining margin ($/bbl) | For refiners only: the profit from turning a barrel of crude into refined products (the "crack spread") | `14.20` |
| `chemical_margin_usd_tonne` | Chemical margin ($/tonne) | For petrochemical companies: the profit per tonne of chemical product made | `285.0` |
| `lifting_cost_usd_boe` | Lifting cost ($/boe) | The cost to extract one barrel of oil from the ground. Lower is better. | `14.80` |
| `planned_maintenance_days` | Planned maintenance (days) | Number of days in the month the field was intentionally shut down for maintenance | `3.0` |
| `unplanned_outage_days` | Unplanned downtime (days) | Number of days lost to unexpected shutdowns — equipment failures, weather, etc. | `0.5` |
| `spill_count` | Spill incidents | Number of oil or chemical spill events recorded in the month | `0` |
| `scope1_2_ktco2e` | Emissions (kt CO₂e) | Direct and energy-related greenhouse gas emissions in thousands of tonnes of CO₂ equivalent | `0.79` |

---

### `reserves_q` — Oil and gas reserve positions

One row per upstream borrower × quarter × scenario. Only companies with `has_reserves = True` appear here.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `borrower_id` | Borrower | Which upstream company | `BRW000042` |
| `as_of_quarter` | Quarter end | When this reserve estimate was calculated | `2022-03-31` |
| `scenario_id` | Scenario | Economic scenario (affects price-driven reserve revisions) | `baseline` |
| `proved_reserves_mmboe` | Proved reserves (mmboe) | Total oil and gas reserves that have been proved with at least 90% confidence, in millions of barrels of oil equivalent | `238.0` |
| `pdp_mmboe` | Proved developed producing (mmboe) | Reserves in fields that are already producing — the highest-quality, most bankable reserves | `148.0` |
| `pdnp_mmboe` | Proved developed non-producing (mmboe) | Reserves in already-drilled wells that are not yet producing (e.g. waiting on infrastructure) | `28.0` |
| `pud_mmboe` | Proved undeveloped (mmboe) | Reserves that have been identified but require future drilling and development to produce | `62.0` |
| `reserve_life_years` | Reserve life (years) | How many years the proved reserves will last at the current production rate. Key metric for RBL lending. | `6.8` |
| `rrr_pct` | Reserve replacement ratio (%) | How much of what was produced in the quarter was replaced by new discoveries or acquisitions. Above 100% means reserves are growing. | `87.0` |
| `reserve_revision_mmboe` | Reserve revision (mmboe) | Change in proved reserves from the prior quarter due to engineering updates or price changes. Negative revisions are a warning signal. | `-4.2` |
| `offshore_share_pct` | Offshore proportion (%) | What percentage of reserves are in offshore fields. Offshore is costlier to produce and much more expensive to decommission. | `22.0` |
| `mature_asset_share_pct` | Mature field proportion (%) | What percentage of assets are in older, declining fields | `48.0` |
| `engineer_report_date` | Engineer report date | When the independent reserve engineer submitted their latest report. Null if the report has been delayed. | `2022-03-15` |
| `independent_engineer_flag` | Independently verified? | `True` if the reserves have been independently certified by a third-party engineering firm | `True` |

---

### `hedge_position_m` — Commodity hedging contracts

One row per hedge instrument × month × scenario. Upstream borrowers use hedges to lock in prices and protect cash flow.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `hedge_id` | Hedge code | Unique identifier for this hedging contract | `HDG01234567` |
| `borrower_id` | Borrower | Which company holds this hedge | `BRW000042` |
| `as_of_month` | Month | The month this hedge value is recorded | `2022-03-31` |
| `scenario_id` | Scenario | Economic scenario | `baseline` |
| `commodity` | Commodity hedged | What is being hedged against price moves | `oil`, `gas` |
| `instrument_type` | Hedge instrument | What type of financial contract was used (see table below) | `collar` |
| `start_date` | Hedge start | When this contract became active | `2021-07-01` |
| `end_date` | Hedge expiry | When this contract stops providing protection | `2022-06-30` |
| `notional_boe_or_mmbtu` | Volume hedged | The total volume of production covered by this contract | `4 800 000` (boe) |
| `fixed_price` | Swap price ($/unit) | For swaps only: the locked-in price the company receives | `72.00` |
| `floor_price` | Floor price ($/unit) | For put options and collars: the minimum price the company receives — their downside protection level | `65.00` |
| `cap_price` | Cap price ($/unit) | For collars: the maximum price the company can receive — what they give up in exchange for the floor | `90.00` |
| `hedged_pct_next_12m_prod` | % of next 12m production hedged | What fraction of the next 12 months' expected production is covered by active hedges | `0.48` (48%) |
| `mtm_usd_m` | Mark-to-market value (USD m) | The current value of this hedge contract — positive means the hedge is making money (current price < floor) | `18.4` |

**Hedge instrument reference:**

| Instrument | Plain English | Borrower pays / receives |
|---|---|---|
| `swap` | Fixed-for-floating swap | Receives a fixed price regardless of market; pays away upside if prices rise |
| `put_option` | Put option | Pays a premium upfront; if prices fall below the floor, receives the difference |
| `collar` | Collar (put + sold call) | Floor protects against price falls; cap limits upside — zero or low net premium |
| `costless_collar` | Zero-cost collar | Same as collar, structured so the premium income from selling the cap equals the put premium |

---

## Facility monitoring tables

### `facility_snapshot_m` — Monthly state of each credit facility

One row per facility × month × scenario. This is the credit officer's monthly dashboard for each loan.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `facility_id` | Facility | Which loan | `FAC0012847` |
| `borrower_id` | Borrower | Which company | `BRW000042` |
| `as_of_month` | Month | When this snapshot was taken | `2022-03-31` |
| `scenario_id` | Scenario | Economic scenario | `baseline` |
| `drawn_usd_m` | Amount drawn (USD m) | How much of the credit limit the borrower has actually borrowed — the live exposure | `210.0` |
| `undrawn_usd_m` | Undrawn amount (USD m) | How much the borrower could still draw but has not yet — the contingent exposure | `140.0` |
| `utilisation_pct` | Utilisation (%) | Drawn amount as a percentage of the total limit | `60.0` |
| `ead_usd_m` | Exposure at Default (USD m) | Estimate of how much Shell would be owed if the borrower defaulted today — drawn plus a fraction of undrawn | `315.0` |
| `interest_rate_all_in_bps` | All-in interest rate (bps) | The total interest rate the borrower is paying, in hundredths of a percent — base rate plus spread | `680` (= 6.80%) |
| `collateral_value_usd_m` | Collateral value (USD m) | Current estimated value of the assets Shell holds as security | `280.0` |
| `collateral_coverage_x` | Collateral coverage (×) | Collateral value divided by drawn amount. Above 1× means the collateral covers the exposure. | `1.33` |
| `borrowing_base_usd_m` | Borrowing base (USD m) | For RBL facilities only: the maximum amount the borrower can draw, derived from the value of their oil reserves. NaN for other facility types. | `295.0` |
| `dpd_days` | Days past due | How many days overdue the borrower's most recent payment is. Zero is current. 90+ triggers automatic default. | `0` |
| `accrual_status` | Accrual status | Whether the loan is still accruing interest normally (`accruing`) or has been placed on non-accrual because repayment is in doubt | `accruing` |
| `stage_ifrs9` | IFRS 9 stage | Under international accounting rules, loans are classified into three stages: Stage 1 = normal, Stage 2 = significantly increased credit risk, Stage 3 = credit-impaired (in or near default) | `1` |
| `watchlist_flag` | On watchlist? | `True` if this loan has been flagged for closer monitoring — a precursor to remedial action | `False` |

---

### `covenant_test_fact` — Results of every financial condition test

One row per facility × covenant × quarter × scenario. This records whether the borrower passed or failed each financial condition test.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `facility_id` | Facility | Which loan the covenant belongs to | `FAC0012847` |
| `covenant_id` | Covenant | Which specific condition was tested | `COV00048371` |
| `as_of_quarter` | Test date | When the test was carried out | `2022-03-31` |
| `scenario_id` | Scenario | Economic scenario | `baseline` |
| `measured_value` | Measured ratio | The actual ratio calculated from the borrower's accounts | `3.82` (leverage) |
| `headroom_pct` | Headroom (%) | How far the measured ratio is from the limit, expressed as a percentage. Positive = passing with room. Negative = breaching. | `-9.1` |
| `breach_flag` | Covenant breach? | `True` if the borrower failed this test | `True` |
| `waiver_flag` | Waiver granted? | `True` if Shell agreed to waive this breach rather than calling an event of default | `False` |
| `cure_end_date` | Cure period deadline | The date by which the borrower must remedy a breach, or a formal default is declared | `2022-04-30` |
| `breach_severity` | How serious? | How badly the borrower has missed the threshold | `minor`, `material`, `critical` |

---

## Credit risk outcome tables

### `rating_history_m` — Credit rating track record

One row per borrower × month × scenario. This shows how Shell's internal view of each borrower's creditworthiness evolves.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `borrower_id` | Borrower | Which company | `BRW000042` |
| `as_of_month` | Month | When this rating was recorded | `2022-03-31` |
| `scenario_id` | Scenario | Economic scenario | `severe_demand` |
| `agency` | Rating source | Where this rating comes from | `internal` |
| `external_rating` | External credit rating | Shell's proxy for what a rating agency would give this borrower. Uses standard S&P/Fitch scale. | `BB-` |
| `outlook` | Rating direction | Whether the rating is expected to improve, stay stable, or worsen | `negative`, `stable`, `positive` |
| `watch_flag` | On rating watch? | `True` if the rating is under review and may be changed soon — a warning signal | `True` |
| `internal_grade` | Shell internal grade | Shell's own credit grade for this borrower — uses the same scale as external ratings | `BB` |
| `internal_pd_1y` | 1-year default probability | Shell's estimate of the probability that this borrower defaults within the next 12 months. Ranges from near-zero for the safest to 45% for the most distressed. | `0.082` (8.2%) |
| `stale_rating_flag` | Stale rating? | `True` if the external rating has not been updated recently — common for private companies | `False` |

**Rating scale reference (from safest to most risky):**

| Rating | Meaning | Typical 1-year default rate |
|---|---|---|
| `AAA` to `AA-` | Highest quality — very unlikely to default | < 0.1% |
| `A+` to `A-` | Strong — well-managed with solid finances | 0.1%–0.3% |
| `BBB+` to `BBB-` | Investment grade — adequate but more sensitive to cycles | 0.4%–0.9% |
| `BB+` to `BB-` | Speculative grade ("junk") — manageable but at risk in downturns | 1.4%–3.1% |
| `B+` to `B-` | High risk — finances are stretched; dependent on commodity prices | 4.5%–9.5% |
| `CCC+` to `C` | Highly distressed — default is a real near-term possibility | 14%–45% |

---

### `default_event_fact` — Every default event recorded

One row per default event × facility. A borrower that defaults on multiple facilities generates multiple rows.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `default_id` | Default code | Unique identifier for this default event | `DEF0001284` |
| `borrower_id` | Borrower | Which company defaulted | `BRW000042` |
| `facility_id` | Facility | Which specific loan defaulted | `FAC0012847` |
| `default_date` | Default date | When the default was formally recognised | `2022-08-31` |
| `scenario_id` | Scenario | Economic scenario | `severe_demand` |
| `default_type` | How it defaulted | Which Basel-defined default trigger applied | `dpd_90`, `unlikely_to_pay`, `bankruptcy`, `distressed_restructuring` |
| `dpd_90_flag` | 90 days past due? | `True` if the trigger was missing three monthly payments | `False` |
| `utp_flag` | Unlikely to pay? | `True` if Shell judged the borrower unlikely to repay even without missing payments (e.g. reserves exhausted, covenant collapse) | `True` |
| `bankruptcy_flag` | Formal bankruptcy? | `True` if the borrower filed for court protection | `True` |
| `distressed_restructuring_flag` | Restructuring? | `True` if Shell agreed to reschedule or write down the debt to avoid formal bankruptcy | `False` |
| `reason_code` | Primary reason | The most significant factor that drove the default | `high_leverage_risk`, `covenant_breach`, `liquidity_deterioration`, `commodity_price_shock`, `refinancing_failure` |
| `default_ead_usd_m` | Exposure at default (USD m) | How much Shell was owed at the moment of default — the starting point for recovery calculations | `295.0` |

---

### `recovery_cashflow_fact` — Cash recovered after a default

One row per default × month during the workout period. A default on a $300m facility might generate 18–36 monthly rows as Shell recovers cash over time.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `default_id` | Default code | Links back to the default event | `DEF0001284` |
| `facility_id` | Facility | Which loan this recovery relates to | `FAC0012847` |
| `borrower_id` | Borrower | Which company | `BRW000042` |
| `scenario_id` | Scenario | Economic scenario | `severe_demand` |
| `recovery_date` | Recovery date | The month in which this cash was collected | `2023-02-28` |
| `gross_recovery_usd_m` | Gross recovery (USD m) | Total cash collected from selling collateral, collecting receivables, or receiving insolvency distributions — before costs | `18.4` |
| `workout_cost_usd_m` | Workout costs (USD m) | Legal fees, valuers, advisers, enforcement costs — what Shell had to spend to recover the money | `1.8` |
| `net_recovery_usd_m` | Net recovery (USD m) | Gross recovery minus workout costs — what Shell actually keeps | `16.6` |
| `discount_rate_bps` | Discount rate (bps) | The rate used to convert future cash flows to present value — needed for ECL calculations. 1000 bps = 10%. | `1000` |
| `collateral_realisation_source` | How recovered | How Shell recovered the money | `reserve_sale`, `asset_sale`, `receivable_collection`, `unsecured_recovery` |
| `resolution_status` | Status | Whether the workout is still ongoing or has concluded | `ongoing`, `resolved` |
| `final_lgd` | Final loss rate | Loss Given Default: the fraction of the original exposure that Shell ultimately loses. Populated only in the final row. 0.35 means Shell lost 35 cents in the dollar. | `0.35` |

---

## Commercial trade book

### `trade_credit_terms_m` — Receivables from Shell's product customers

One row per commercial customer × month × scenario. This covers companies that buy petroleum products, LNG, chemicals, and other products from Shell on credit.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `customer_id` | Customer code | Which counterparty (links to `counterparty_dim`) | `CPT000318` |
| `as_of_month` | Month | When this snapshot was taken | `2022-03-31` |
| `scenario_id` | Scenario | Economic scenario | `severe_demand` |
| `payment_terms_days` | Payment terms (days) | How many days after delivery the customer must pay. Shorter terms for riskier customers. | `30` |
| `approved_credit_limit_usd_m` | Approved credit limit (USD m) | The maximum unpaid balance Shell will allow this customer to carry at any one time | `12.0` |
| `temporary_credit_limit_usd_m` | Temporary limit (USD m) | A short-term increase to the credit limit, sometimes granted to cover a large seasonal shipment | `14.5` |
| `current_ar_usd_m` | Total outstanding (USD m) | Total money owed to Shell by this customer right now — all ageing buckets combined | `8.4` |
| `ar_not_due_usd_m` | Not yet due (USD m) | Invoices that have been raised but the payment date has not yet arrived | `5.2` |
| `ar_1_30_dpd_usd_m` | 1–30 days overdue (USD m) | Invoices that are up to one month late | `1.8` |
| `ar_31_60_dpd_usd_m` | 31–60 days overdue (USD m) | Invoices that are one to two months late | `0.9` |
| `ar_61_90_dpd_usd_m` | 61–90 days overdue (USD m) | Invoices two to three months late — credit team is actively chasing | `0.4` |
| `ar_90_plus_dpd_usd_m` | Over 90 days overdue (USD m) | Invoices more than three months late — serious concern; may need legal action or provision | `0.1` |
| `utilisation_pct` | Credit utilisation (%) | Total outstanding as a percentage of the approved credit limit. Over 100% means the customer has exceeded their limit. | `70.0` |
| `blocked_order_flag` | Orders blocked? | `True` if Shell has stopped taking new orders from this customer until overdue amounts are cleared | `False` |
| `credit_hold_flag` | On credit hold? | `True` if Shell has frozen credit — deliveries continue only against cash in advance or with additional security | `True` |
| `letter_of_credit_flag` | Letter of credit required? | `True` if Shell requires this customer to provide a bank letter of credit to guarantee payment | `True` |
| `guarantee_flag` | Parent guarantee in place? | `True` if a parent company or third party has guaranteed this customer's payments | `False` |
| `credit_insurance_flag` | Credit insurance in place? | `True` if Shell has bought trade credit insurance against non-payment by this customer | `True` |
| `collateral_required_flag` | Collateral required? | `True` if the customer has had to post assets or cash as security | `False` |
| `collateral_value_usd_m` | Collateral value (USD m) | Value of the security posted | `0.0` |
| `last_credit_review_date` | Last review date | When Shell last formally reassessed this customer's credit limit and terms | `2022-01-31` |
| `next_review_due_date` | Next review due | When Shell must review the credit limit again | `2023-01-31` |

---

## Commodity trading book

### `trading_exposure_m` — Exposure to commodity trading counterparties

One row per counterparty × commodity × month × scenario. This covers companies Shell trades derivatives, physical cargoes, and gas/power with.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `counterparty_id` | Counterparty | Which trading counterparty (links to `counterparty_dim`) | `CPT000085` |
| `commodity` | Commodity | What product is being traded | `crude_oil`, `lng`, `natural_gas`, `diesel`, `naphtha`, `power`, `chemicals`, `bunker_fuel` |
| `as_of_month` | Month | When this exposure was measured | `2022-03-31` |
| `scenario_id` | Scenario | Economic scenario | `geopolitical_supply` |
| `contract_type` | Position direction | Whether Shell is owed money (long position) or owes money (short) in this trade | `long_physical`, `short_physical` |
| `gross_receivable_usd_m` | Gross receivable (USD m) | The total amount the counterparty owes Shell — before netting or collateral | `42.0` |
| `gross_payable_usd_m` | Gross payable (USD m) | The total amount Shell owes the counterparty — before netting | `18.0` |
| `net_exposure_usd_m` | Net credit exposure (USD m) | After applying netting agreements and deducting collateral received — the real economic exposure Shell is taking | `15.2` |
| `mtm_positive_usd_m` | Mark-to-market gain (USD m) | The value of contracts where Shell is in-the-money — i.e. Shell would receive this much if the counterparty settled today | `28.0` |
| `mtm_negative_usd_m` | Mark-to-market loss (USD m) | The value of contracts where Shell is out-of-the-money — Shell would owe this much if settled today | `12.0` |
| `settlement_exposure_usd_m` | Settlement exposure (USD m) | Money owed for physical deliveries already made but not yet cash-settled — the most immediate form of exposure | `8.5` |
| `replacement_cost_usd_m` | Replacement cost (USD m) | How much it would cost Shell to replace a defaulted contract at current market prices | `22.0` |
| `pfe_usd_m` | Potential Future Exposure (USD m) | A statistical estimate (95th percentile) of how large the exposure could grow before the contract matures — the peak credit risk | `38.5` |
| `netting_agreement_flag` | Netting agreement? | `True` if Shell and this counterparty have agreed to net their mutual obligations — reduces gross exposure to net | `True` |
| `csa_flag` | Credit Support Annex? | `True` if a margin/collateral agreement is in place — the losing party must post cash or securities as the trade moves against them | `True` |
| `collateral_posted_usd_m` | Collateral posted by Shell (USD m) | Cash or securities Shell has had to provide as the trade moved against it | `11.0` |
| `collateral_received_usd_m` | Collateral received (USD m) | Cash or securities the counterparty has posted because the trade moved in Shell's favour | `25.0` |
| `margin_call_amount_usd_m` | Margin call outstanding (USD m) | Additional collateral demanded from the counterparty that has not yet been paid — a warning signal | `0.0` |
| `wrong_way_risk_flag` | Wrong-way risk? | `True` if this counterparty's ability to pay tends to deteriorate exactly when Shell's exposure to them is largest — e.g. an oil producer exposed to the same low oil prices that increase Shell's claim on them | `True` |
| `country_concentration_flag` | Country risk concern? | `True` if the counterparty is based in a country with elevated political, sanctions, or transfer risk | `False` |
| `limit_breach_flag` | Over credit limit? | `True` if the net exposure has exceeded the approved trading limit — requires immediate remedial action | `False` |
| `approved_limit_usd_m` | Approved trading limit (USD m) | The maximum net credit exposure Shell's credit team has approved for this counterparty in this commodity | `20.0` |

---

## Supporting tables

### `transaction_fact` — Individual financial transactions

One row per transaction. A sample of drawdowns, repayments, interest payments, and fees processed through Shell's credit systems. Includes a small number of deliberate duplicates to reflect real system imperfections.

| Column | Plain label | What it means | Example |
|---|---|---|---|
| `txn_id` | Transaction code | Unique identifier | `TXN000284761` |
| `facility_id` | Facility | Which loan this transaction relates to | `FAC0012847` |
| `borrower_id` | Borrower | Which company | `BRW000042` |
| `txn_date` | Transaction date | When the transaction occurred | `2022-03-15` |
| `txn_type` | Transaction type | What kind of financial movement this was | `drawdown`, `repayment`, `interest_payment`, `fee_payment`, `rollover` |
| `amount_usd` | Amount (USD) | The transaction value in US dollars (not millions) | `25 000 000` |
| `currency` | Currency | Currency of the transaction | `USD` |
| `commodity_ref` | Commodity reference | For trade-finance transactions, which commodity the transaction relates to | `null` or `crude_oil` |
| `settlement_status` | Settlement status | Whether the transaction has been fully settled or is still pending in the payment system | `settled`, `pending` |
| `days_to_settle` | Days to settle | How many working days between trade date and cash settlement | `0`, `1`, `2`, `3` |

---

## Data quality flags to watch for

The dataset deliberately includes realistic data imperfections, consistent with what credit teams encounter in production systems.

| Flag / symptom | Where it appears | What it means | How common |
|---|---|---|---|
| `filing_lag_flag = True` | `borrower_financials_q` | Financial results have been filed late — NaN values in key financial columns for this row | 3–8% of private company quarters |
| `reserve_report_delay_flag = True` | `reserves_q` | The independent engineer's report was not submitted on time — `independent_engineer_flag` set to False | 5–10% of upstream quarter-ends |
| NaN in `floor_price` or `cap_price` | `hedge_position_m` | Smaller private borrowers partially disclosed their hedge — notional is known but instrument terms are missing | 10–20% of smaller borrower hedge rows |
| `unit_conversion_suspect = True` | `borrower_operations_m` | A production figure may have a unit error (e.g. confused barrels and cubic feet — a factor of 5.6× difference) | 0.1–0.3% of rows |
| `restatement_flag = True` | `borrower_financials_q` | This quarter's financials were subsequently restated — treat with care when comparing to prior periods | 1–3% of borrower histories |
| `stale_rating_flag = True` | `rating_history_m` | The external rating has not been updated for several months — the internal grade is more current | 2–5% of unlisted borrower months |
| Duplicate `txn_id` | `transaction_fact` | The same transaction was accidentally recorded twice in the payment system | ~0.05% of transaction rows |
| `kyc_status = pending` or `flagged` | `counterparty_dim` | This counterparty's KYC verification is incomplete or has raised a concern | ~5% of counterparties |
| `sanctions_flag = True` | `counterparty_dim` | This counterparty is associated with a sanctions list — in practice, no transactions should occur | ~0.5% of counterparties |

---

## Key relationships between tables

```
borrower_dim ──────────────────── borrower_id ──┬── borrower_financials_q
                                                 ├── borrower_operations_m
                                                 ├── reserves_q
                                                 ├── hedge_position_m
                                                 ├── rating_history_m
                                                 └── facility_dim ──── facility_id ──┬── covenant_def_dim ── covenant_id ── covenant_test_fact
                                                                                      ├── facility_snapshot_m
                                                                                      ├── default_event_fact ── default_id ── recovery_cashflow_fact
                                                                                      └── transaction_fact

counterparty_dim ────────────────── counterparty_id ──┬── trade_credit_terms_m  (as customer_id)
                                                       └── trading_exposure_m

macro_scenario_m ─────────────── scenario_id + as_of_month ─── (drives all time-series tables)
```

---

*Data dictionary generated for the Credit Analytics synthetic dataset.*
*All values are synthetic and have been generated using the equations and calibration described in `Credit Analytics.md`.*
*No real company financial data has been used.*
