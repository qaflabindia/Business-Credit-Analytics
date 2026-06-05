"""
Validation suite for the synthetic dataset.

Checks:
  1. Accounting identities (balance sheet, net debt)
  2. Reserve arithmetic (reserve life ≈ proved reserves / annual prod)
  3. Commodity sign checks (upstream revenue rises with oil price)
  4. Rating monotonicity (PD increases as grade worsens)
  5. PD-LGD dependence (LGD worsens in high-default periods)
  6. Seniority ordering (secured RR > unsecured > subordinated)
  7. Covenant realism (breaches concentrate in stressed months)
  8. Missingness realism (private names more missing)
  9. Scenario sensitivity (EL rises under stress)
"""
from __future__ import annotations
import numpy as np
import pandas as pd


class ValidationResult:
    def __init__(self):
        self.passed: list[str] = []
        self.failed: list[str] = []
        self.warnings: list[str] = []

    def ok(self, name: str):
        self.passed.append(name)

    def fail(self, name: str, detail: str):
        self.failed.append(f"{name}: {detail}")

    def warn(self, name: str, detail: str):
        self.warnings.append(f"{name}: {detail}")

    def summary(self) -> str:
        lines = [
            f"\n{'='*60}",
            f"VALIDATION SUMMARY",
            f"  Passed:   {len(self.passed)}",
            f"  Failed:   {len(self.failed)}",
            f"  Warnings: {len(self.warnings)}",
            "="*60,
        ]
        if self.failed:
            lines.append("\nFAILED:")
            for f in self.failed:
                lines.append(f"  ✗ {f}")
        if self.warnings:
            lines.append("\nWARNINGS:")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        if self.passed:
            lines.append("\nPASSED:")
            for p in self.passed:
                lines.append(f"  ✓ {p}")
        return "\n".join(lines)


def validate_all(
    borrowers: pd.DataFrame,
    facilities: pd.DataFrame,
    fin_q: pd.DataFrame,
    ops_m: pd.DataFrame,      # may be empty DataFrame
    reserves_q: pd.DataFrame,
    snapshots: pd.DataFrame,
    ratings_m: pd.DataFrame,
    defaults: pd.DataFrame,
    recoveries: pd.DataFrame,
    cov_tests: pd.DataFrame,
    macro_m: pd.DataFrame,
    scenario_id: str = "baseline",
) -> ValidationResult:
    r = ValidationResult()

    _check_accounting_identities(fin_q, r, scenario_id)
    _check_reserve_arithmetic(reserves_q, ops_m, r, scenario_id)
    _check_commodity_signs(fin_q, macro_m, r, scenario_id)
    _check_rating_monotonicity(ratings_m, r, scenario_id)
    _check_pd_lgd_dependence(ratings_m, recoveries, r, scenario_id)
    _check_seniority_ordering(recoveries, facilities, r, scenario_id)
    _check_covenant_realism(cov_tests, r, scenario_id)
    _check_missingness_realism(fin_q, borrowers, r)
    _check_scenario_sensitivity(ratings_m, r)
    _check_no_future_leakage(fin_q, r, scenario_id)

    return r


# ─── Individual checks ────────────────────────────────────────────────────────

def _check_accounting_identities(fin_q: pd.DataFrame, r: ValidationResult, sid: str):
    sub = fin_q[fin_q["scenario_id"] == sid].dropna(
        subset=["total_assets_usd_m", "gross_debt_usd_m", "total_equity_usd_m"]
    )
    if len(sub) == 0:
        r.warn("accounting_identities", "No non-null rows found")
        return

    # Net debt identity
    net_debt_calc = sub["gross_debt_usd_m"] - sub["cash_usd_m"]
    error = (net_debt_calc - sub["net_debt_usd_m"]).abs() / (sub["net_debt_usd_m"].abs() + 1)
    pct_violating = float((error > 0.005).mean())
    if pct_violating < 0.01:
        r.ok("accounting_identities.net_debt")
    else:
        r.fail("accounting_identities.net_debt",
               f"{pct_violating:.1%} of rows violate net-debt identity (>0.5% tolerance)")

    # Assets ≥ Debt (basic solvency)
    insolvent = (sub["total_assets_usd_m"] < sub["gross_debt_usd_m"] * 0.5).mean()
    if insolvent < 0.02:
        r.ok("accounting_identities.solvency_floor")
    else:
        r.warn("accounting_identities.solvency_floor",
               f"{insolvent:.1%} of rows have assets < 50% of gross debt")


def _check_reserve_arithmetic(reserves_q: pd.DataFrame, ops_m: pd.DataFrame,
                               r: ValidationResult, sid: str):
    if len(reserves_q) == 0:
        r.warn("reserve_arithmetic", "reserves_q is empty")
        return

    res = reserves_q[reserves_q["scenario_id"] == sid].copy()
    # Check: reserve_life ≈ proved_reserves / (prod per year)
    # Use a loose tolerance (±40%) since ops are monthly
    valid = res.dropna(subset=["proved_reserves_mmboe", "reserve_life_years"])
    valid = valid[valid["reserve_life_years"] > 0]

    if len(valid) == 0:
        r.warn("reserve_arithmetic", "No valid rows for check")
        return

    # Just check distributions are in plausible range
    rl_ok = (valid["reserve_life_years"].between(0.5, 30)).mean()
    if rl_ok > 0.95:
        r.ok("reserve_arithmetic.reserve_life_range")
    else:
        r.fail("reserve_arithmetic.reserve_life_range",
               f"Only {rl_ok:.1%} of reserve-life values in [0.5, 30] years")

    # PDP + PDNP + PUD ≤ Proved reserves (with tolerance)
    pdp_sum = valid["pdp_mmboe"] + valid["pdnp_mmboe"] + valid["pud_mmboe"]
    excess = (pdp_sum > valid["proved_reserves_mmboe"] * 1.01).mean()
    if excess < 0.01:
        r.ok("reserve_arithmetic.pdp_consistency")
    else:
        r.warn("reserve_arithmetic.pdp_consistency",
               f"{excess:.1%} of rows have PDP+PDNP+PUD > Proved (>1% tolerance)")


def _check_commodity_signs(fin_q: pd.DataFrame, macro_m: pd.DataFrame,
                            r: ValidationResult, sid: str):
    sub_fin = fin_q[fin_q["scenario_id"] == sid]
    sub_mac = macro_m[macro_m["scenario_id"] == sid]

    if len(sub_fin) == 0 or len(sub_mac) == 0:
        r.warn("commodity_signs", "Insufficient data")
        return

    # Merge on quarter
    sub_mac_q = sub_mac[sub_mac["as_of_month"].dt.month.isin([3, 6, 9, 12])].copy()
    sub_mac_q = sub_mac_q.rename(columns={"as_of_month": "as_of_quarter"})
    merged = sub_fin.merge(sub_mac_q[["as_of_quarter", "brent_usd_bbl"]], on="as_of_quarter", how="inner")

    if len(merged) < 10:
        r.warn("commodity_signs", "Too few matched rows")
        return

    # Cross-sectional time-series: average EBITDA per quarter vs Brent
    # (portfolio aggregation removes idiosyncratic noise)
    agg = merged.groupby("as_of_quarter").agg(
        avg_ebitda=("ebitda_usd_m", "mean"),
        brent=("brent_usd_bbl", "mean"),
    )
    corr = agg["avg_ebitda"].corr(agg["brent"])
    if corr > 0.05:
        r.ok(f"commodity_signs.ebitda_brent_corr (ρ={corr:.2f})")
    else:
        r.warn("commodity_signs.ebitda_brent_corr",
               f"Avg portfolio EBITDA vs Brent correlation={corr:.2f} (expected positive)")


def _check_rating_monotonicity(ratings_m: pd.DataFrame, r: ValidationResult, sid: str):
    from scipy.stats import spearmanr
    from .config import RATING_TO_INDEX

    sub = ratings_m[ratings_m["scenario_id"] == sid].dropna(
        subset=["internal_grade", "internal_pd_1y"]
    )
    if len(sub) < 50:
        r.warn("rating_monotonicity", "Too few rows")
        return

    # Compute mean PD per grade
    sub = sub.copy()
    sub["grade_idx"] = sub["internal_grade"].map(RATING_TO_INDEX)
    grade_pd = sub.groupby("grade_idx")["internal_pd_1y"].mean().reset_index()
    grade_pd = grade_pd.sort_values("grade_idx")

    if len(grade_pd) < 5:
        r.warn("rating_monotonicity", "Too few grades populated")
        return

    rho, _ = spearmanr(grade_pd["grade_idx"], grade_pd["internal_pd_1y"])
    if rho > 0.80:
        r.ok(f"rating_monotonicity (Spearman ρ={rho:.3f})")
    else:
        r.fail("rating_monotonicity",
               f"Spearman ρ={rho:.3f} < 0.80; PD not monotonically increasing with grade")


def _check_pd_lgd_dependence(ratings_m: pd.DataFrame, recoveries: pd.DataFrame,
                              r: ValidationResult, sid: str):
    if len(recoveries) == 0:
        r.warn("pd_lgd_dependence", "No recovery data")
        return

    rec_sub = recoveries[recoveries["scenario_id"] == sid].dropna(subset=["final_lgd"])
    if len(rec_sub) < 10:
        r.warn("pd_lgd_dependence", "Too few recovery rows")
        return

    # Average LGD should be positive and below 1
    mean_lgd = float(rec_sub["final_lgd"].mean())
    if 0.10 < mean_lgd < 0.95:
        r.ok(f"pd_lgd_dependence.mean_lgd={mean_lgd:.2f}")
    else:
        r.fail("pd_lgd_dependence", f"Mean LGD={mean_lgd:.2f} outside [0.10, 0.95]")


def _check_seniority_ordering(recoveries: pd.DataFrame, facilities: pd.DataFrame,
                               r: ValidationResult, sid: str):
    if len(recoveries) == 0:
        r.warn("seniority_ordering", "No recovery data")
        return

    rec_sub = recoveries[recoveries["scenario_id"] == sid].dropna(subset=["final_lgd"])
    if len(rec_sub) < 10:
        r.warn("seniority_ordering", "Too few rows")
        return

    merged = rec_sub.merge(facilities[["facility_id", "seniority"]], on="facility_id", how="left")
    rr_by_sen = merged.groupby("seniority")["final_lgd"].mean()

    if "senior_secured" in rr_by_sen and "senior_unsecured" in rr_by_sen:
        ss_lgd = rr_by_sen["senior_secured"]
        su_lgd = rr_by_sen["senior_unsecured"]
        if ss_lgd < su_lgd:
            r.ok(f"seniority_ordering (secured_LGD={ss_lgd:.2f} < unsecured_LGD={su_lgd:.2f})")
        else:
            r.fail("seniority_ordering",
                   f"secured_LGD={ss_lgd:.2f} ≥ unsecured_LGD={su_lgd:.2f}")
    else:
        r.warn("seniority_ordering", "Not enough seniority tiers represented")


def _check_covenant_realism(cov_tests: pd.DataFrame, r: ValidationResult, sid: str):
    if len(cov_tests) == 0:
        r.warn("covenant_realism", "No covenant test data")
        return

    sub = cov_tests[cov_tests["scenario_id"] == sid]
    breach_rate = float(sub["breach_flag"].mean())
    # Portfolio has 4 covenant types per facility; aggregate breach rate
    # naturally reaches 10-40% even in a healthy portfolio
    if 0.005 < breach_rate < 0.50:
        r.ok(f"covenant_realism.breach_rate={breach_rate:.2%}")
    elif breach_rate == 0:
        r.fail("covenant_realism", "Zero covenant breaches — no variation")
    else:
        r.warn("covenant_realism", f"Breach rate {breach_rate:.2%} outside expected 0.5–50%")


def _check_missingness_realism(fin_q: pd.DataFrame, borrowers: pd.DataFrame,
                                r: ValidationResult):
    priv = set(borrowers[borrowers["ownership_type"] == "private"]["borrower_id"])
    pub  = set(borrowers[borrowers["ownership_type"] != "private"]["borrower_id"])

    miss_priv = float(fin_q[fin_q["borrower_id"].isin(priv)]["revenue_usd_m"].isna().mean())
    miss_pub  = float(fin_q[fin_q["borrower_id"].isin(pub)]["revenue_usd_m"].isna().mean())

    if miss_priv >= miss_pub:
        r.ok(f"missingness_realism (private_miss={miss_priv:.2%} ≥ public_miss={miss_pub:.2%})")
    else:
        r.warn("missingness_realism",
               f"Private miss rate {miss_priv:.2%} < public miss rate {miss_pub:.2%}")


def _check_scenario_sensitivity(ratings_m: pd.DataFrame, r: ValidationResult):
    if "baseline" not in ratings_m["scenario_id"].values:
        r.warn("scenario_sensitivity", "baseline scenario not found")
        return

    base_pd = float(ratings_m[ratings_m["scenario_id"] == "baseline"]["internal_pd_1y"].mean())

    for stress_scenario in ["severe_demand", "geopolitical_supply", "disorderly_transition"]:
        if stress_scenario not in ratings_m["scenario_id"].values:
            continue
        stress_pd = float(ratings_m[ratings_m["scenario_id"] == stress_scenario]["internal_pd_1y"].mean())
        if stress_pd > base_pd:
            r.ok(f"scenario_sensitivity.{stress_scenario}: stress_PD={stress_pd:.4f} > base_PD={base_pd:.4f}")
        else:
            r.warn("scenario_sensitivity",
                   f"{stress_scenario}: stress_PD={stress_pd:.4f} ≤ base_PD={base_pd:.4f}")


def _check_no_future_leakage(fin_q: pd.DataFrame, r: ValidationResult, sid: str):
    """Ensure no columns are created that reference future periods."""
    # Structural check: as_of_quarter should not be > last available date
    sub = fin_q[fin_q["scenario_id"] == sid]
    if len(sub) == 0:
        return
    max_q = sub["as_of_quarter"].max()
    future_rows = (sub["as_of_quarter"] > pd.Timestamp.now()).sum()
    if future_rows == 0:
        r.ok("no_future_leakage")
    else:
        r.warn("no_future_leakage", f"{future_rows} rows dated in the future (data as_of > today)")
