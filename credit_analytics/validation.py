"""
Validation suite for the O&G business AR synthetic dataset.

Checks:
  1. AR bucket consistency (sum of buckets ≈ total AR)
  2. Credit limits positive and bounded
  3. Utilisation distribution (should not be uniformly 0 or >200%)
  4. Credit holds correlate with overdue concentration
  5. Overdue rates rise under stress vs baseline
  6. Commodity-risk customers have higher overdue rates
  7. Payment terms within allowed range per tier
"""
from __future__ import annotations
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
            "VALIDATION SUMMARY",
            f"  Passed:   {len(self.passed)}",
            f"  Failed:   {len(self.failed)}",
            f"  Warnings: {len(self.warnings)}",
            "="*60,
        ]
        if self.failed:
            lines.append("\nFAILED:")
            for f in self.failed:
                lines.append(f"  x {f}")
        if self.warnings:
            lines.append("\nWARNINGS:")
            for w in self.warnings:
                lines.append(f"  ! {w}")
        if self.passed:
            lines.append("\nPASSED:")
            for p in self.passed:
                lines.append(f"  + {p}")
        return "\n".join(lines)


def validate_all(
    customers: pd.DataFrame,
    ar_m: pd.DataFrame,
    macro_m: pd.DataFrame,
    scenario_id: str = "baseline",
) -> ValidationResult:
    r = ValidationResult()

    if len(ar_m) == 0:
        r.warn("all_checks", "AR table is empty — no validation performed")
        return r

    sub = ar_m[ar_m["scenario_id"] == scenario_id]
    if len(sub) == 0:
        r.warn("all_checks", f"No rows for scenario '{scenario_id}'")
        return r

    _check_bucket_consistency(sub, r)
    _check_credit_limits(sub, r)
    _check_utilisation_distribution(sub, r)
    _check_hold_overdue_correlation(sub, r)
    _check_stress_sensitivity(ar_m, r)
    _check_commodity_risk_customers(ar_m, customers, r, scenario_id)
    _check_payment_terms_range(sub, r)

    return r


def _check_bucket_consistency(sub: pd.DataFrame, r: ValidationResult):
    bucket_sum = (
        sub["ar_not_due_usd_m"]
        + sub["ar_1_30_dpd_usd_m"]
        + sub["ar_31_60_dpd_usd_m"]
        + sub["ar_61_90_dpd_usd_m"]
        + sub["ar_90_plus_dpd_usd_m"]
    )
    total = sub["current_ar_usd_m"]
    error_pct = ((bucket_sum - total).abs() / total.clip(lower=0.001)).mean()
    if error_pct < 0.01:
        r.ok("bucket_consistency")
    else:
        r.fail("bucket_consistency",
               f"Mean relative error between bucket sum and total AR = {error_pct:.2%}")


def _check_credit_limits(sub: pd.DataFrame, r: ValidationResult):
    bad = (sub["approved_credit_limit_usd_m"] <= 0).mean()
    if bad < 0.001:
        r.ok("credit_limits_positive")
    else:
        r.fail("credit_limits_positive",
               f"{bad:.2%} of rows have non-positive approved credit limits")

    huge = (sub["approved_credit_limit_usd_m"] > 1_000).mean()
    if huge < 0.001:
        r.ok("credit_limits_bounded")
    else:
        r.warn("credit_limits_bounded",
               f"{huge:.2%} of rows have approved limit > USD 1 000m")


def _check_utilisation_distribution(sub: pd.DataFrame, r: ValidationResult):
    zero_ar = (sub["current_ar_usd_m"] <= 0).mean()
    if zero_ar < 0.20:
        r.ok(f"utilisation_distribution (zero_AR={zero_ar:.1%})")
    else:
        r.warn("utilisation_distribution",
               f"{zero_ar:.1%} of rows have zero AR — may be too sparse")

    over_limit = (sub["utilisation_pct"] > 150).mean()
    if over_limit < 0.05:
        r.ok(f"utilisation_cap (over_150pct={over_limit:.1%})")
    else:
        r.warn("utilisation_cap",
               f"{over_limit:.1%} of rows exceed 150% utilisation")


def _check_hold_overdue_correlation(sub: pd.DataFrame, r: ValidationResult):
    hold_rows = sub[sub["credit_hold_flag"]]
    no_hold_rows = sub[~sub["credit_hold_flag"]]
    if len(hold_rows) == 0 or len(no_hold_rows) == 0:
        r.warn("hold_overdue_correlation", "No credit-hold variation")
        return

    overdue_col = (
        sub["ar_1_30_dpd_usd_m"]
        + sub["ar_31_60_dpd_usd_m"]
        + sub["ar_61_90_dpd_usd_m"]
        + sub["ar_90_plus_dpd_usd_m"]
    ) / sub["approved_credit_limit_usd_m"].clip(lower=0.001)

    hold_overdue = float(overdue_col[sub["credit_hold_flag"]].mean())
    no_hold_overdue = float(overdue_col[~sub["credit_hold_flag"]].mean())
    if hold_overdue > no_hold_overdue:
        r.ok(f"hold_overdue_correlation "
             f"(hold={hold_overdue:.2%} > no_hold={no_hold_overdue:.2%})")
    else:
        r.fail("hold_overdue_correlation",
               f"hold_overdue={hold_overdue:.2%} not > no_hold_overdue={no_hold_overdue:.2%}")


def _check_stress_sensitivity(ar_m: pd.DataFrame, r: ValidationResult):
    if "baseline" not in ar_m["scenario_id"].values:
        r.warn("stress_sensitivity", "baseline scenario not in table")
        return

    base_overdue = _mean_overdue_rate(ar_m, "baseline")
    for stress in ["severe_demand", "geopolitical_supply", "disorderly_transition"]:
        if stress not in ar_m["scenario_id"].values:
            continue
        stress_overdue = _mean_overdue_rate(ar_m, stress)
        if stress_overdue > base_overdue:
            r.ok(f"stress_sensitivity.{stress} "
                 f"(stress={stress_overdue:.3%} > base={base_overdue:.3%})")
        else:
            r.warn("stress_sensitivity",
                   f"{stress}: overdue rate {stress_overdue:.3%} not above baseline {base_overdue:.3%}")


def _mean_overdue_rate(ar_m: pd.DataFrame, scenario: str) -> float:
    sub = ar_m[ar_m["scenario_id"] == scenario]
    overdue = (
        sub["ar_1_30_dpd_usd_m"]
        + sub["ar_31_60_dpd_usd_m"]
        + sub["ar_61_90_dpd_usd_m"]
        + sub["ar_90_plus_dpd_usd_m"]
    )
    total = sub["current_ar_usd_m"].clip(lower=0.001)
    return float((overdue / total).mean())


def _check_commodity_risk_customers(
    ar_m: pd.DataFrame, customers: pd.DataFrame,
    r: ValidationResult, scenario: str,
):
    sub = ar_m[ar_m["scenario_id"] == scenario]
    risk_ids = set(customers[customers["commodity_risk_flag"]]["customer_id"])
    safe_ids = set(customers[~customers["commodity_risk_flag"]]["customer_id"])

    risk_rows = sub[sub["customer_id"].isin(risk_ids)]
    safe_rows = sub[sub["customer_id"].isin(safe_ids)]
    if len(risk_rows) == 0 or len(safe_rows) == 0:
        r.warn("commodity_risk_check", "Insufficient coverage")
        return

    risk_overdue = _overdue_rate_df(risk_rows)
    safe_overdue = _overdue_rate_df(safe_rows)
    if risk_overdue >= safe_overdue:
        r.ok(f"commodity_risk_check "
             f"(risk={risk_overdue:.3%} >= safe={safe_overdue:.3%})")
    else:
        r.warn("commodity_risk_check",
               f"Commodity-risk customers ({risk_overdue:.3%}) not above safe ({safe_overdue:.3%})")


def _overdue_rate_df(df: pd.DataFrame) -> float:
    overdue = (
        df["ar_1_30_dpd_usd_m"]
        + df["ar_31_60_dpd_usd_m"]
        + df["ar_61_90_dpd_usd_m"]
        + df["ar_90_plus_dpd_usd_m"]
    )
    return float((overdue / df["current_ar_usd_m"].clip(lower=0.001)).mean())


def _check_payment_terms_range(sub: pd.DataFrame, r: ValidationResult):
    bad = ((sub["payment_terms_days"] < 7) | (sub["payment_terms_days"] > 90)).mean()
    if bad < 0.001:
        r.ok("payment_terms_range (7–90 days)")
    else:
        r.fail("payment_terms_range",
               f"{bad:.2%} of rows have payment terms outside [7, 90] days")
