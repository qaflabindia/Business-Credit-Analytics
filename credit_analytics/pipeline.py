"""
Memory-efficient pipeline: one scenario at a time, streamed to parquet.

For scenario-specific large tables (financials, operations, reserves, hedges,
snapshots, covenants, ratings, defaults, recoveries) each scenario is written
to a partitioned parquet file immediately after generation; the accumulated
DataFrames are then deleted to keep memory below ~2 GB.

Static tables (borrower_dim, facility_dim, covenant_def_dim, macro_scenario_m)
are written once at the end.
"""
from __future__ import annotations
import gc
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import Config, SEEDS
from .generators.calendar   import make_calendar
from .generators.macro      import generate_macro_paths
from .generators.borrowers  import generate_borrowers
from .generators.facilities import generate_facilities
from .generators.financials import simulate_financials_quarterly
from .generators.operations import simulate_operations_monthly
from .generators.reserves         import simulate_reserves_quarterly
from .generators.hedges           import simulate_hedges_monthly
from .generators.snapshots        import build_facility_snapshots
from .generators.covenants        import test_covenants
from .generators.ratings          import update_ratings
from .generators.defaults         import simulate_defaults
from .generators.recoveries       import simulate_recoveries
from .generators.counterparties   import generate_counterparties
from .generators.trade_credit     import simulate_trade_credit_monthly
from .generators.trading_exposure import simulate_trading_exposure_monthly
from .noise                       import inject_noise
from .validation                  import validate_all

log = logging.getLogger(__name__)


def run(cfg: Config | None = None, verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Execute the full pipeline and return all tables as a dict."""
    if cfg is None:
        cfg = Config()

    if verbose:
        logging.basicConfig(level=logging.INFO,
                            format="%(asctime)s  %(levelname)-7s  %(message)s",
                            datefmt="%H:%M:%S")

    out_dir = Path(cfg.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    _step("Pipeline start",
          f"scale={cfg.scale}  borrowers={cfg.n_borrowers}  "
          f"months={cfg.n_months}  scenarios={cfg.generate_scenarios}")

    # ── 1. Calendar ───────────────────────────────────────────────────────────
    months, quarters = make_calendar(cfg.start_date, cfg.n_months)
    _step("Calendar", f"{len(months)} months  {len(quarters)} quarters")

    # ── 2. Macro ──────────────────────────────────────────────────────────────
    macro_m = generate_macro_paths(
        cfg.n_months, months,
        rng=np.random.default_rng(SEEDS["macro"]),
        scenarios=cfg.generate_scenarios,
    )
    _step("Macro", f"{len(macro_m):,} rows  scenarios={macro_m['scenario_id'].nunique()}")

    # ── 3. Borrowers ──────────────────────────────────────────────────────────
    borrowers = generate_borrowers(
        cfg.n_borrowers,
        rng=np.random.default_rng(SEEDS["borrowers"]),
    )
    _step("Borrowers", f"{len(borrowers):,} rows  "
          f"segments={borrowers['segment'].value_counts().to_dict()}")

    # ── 4. Facilities + covenants ─────────────────────────────────────────────
    facilities, covenant_defs = generate_facilities(
        borrowers,
        rng=np.random.default_rng(SEEDS["facilities"]),
        start_date=cfg.start_date,
    )
    _step("Facilities",
          f"{len(facilities):,} facilities  {len(covenant_defs):,} covenant defs")

    # ── 4b. Counterparties (trading + commercial credit books) ────────────────
    # Scale: ~50% of borrower count, minimum 500
    n_counterparties = max(500, cfg.n_borrowers // 2)
    counterparties = generate_counterparties(
        n_counterparties,
        rng=np.random.default_rng(SEEDS["borrowers"] + 1),
    )
    _step("Counterparties",
          f"{len(counterparties):,} rows  "
          f"types={counterparties['counterparty_type'].value_counts().to_dict()}")

    # Writers: one ParquetWriter per large table (scenario-partitioned)
    writers: dict[str, pq.ParquetWriter] = {}

    def _append(name: str, df: pd.DataFrame):
        """Append df to parquet file for `name`, creating writer on first call."""
        if len(df) == 0:
            return
        table = pa.Table.from_pandas(df, preserve_index=False)
        if name not in writers:
            path = out_dir / f"{name}.parquet"
            writers[name] = pq.ParquetWriter(str(path), table.schema)
        writers[name].write_table(table)

    # Baseline tables for validation (retained in memory)
    baseline_fin_q = baseline_ratings = baseline_defaults = baseline_recoveries = None
    baseline_ops_m = baseline_res_q = baseline_snaps = baseline_cov = None
    baseline_hedges = None

    # ── 5–13. Per-scenario generation, streamed to parquet ───────────────────
    for scenario in cfg.generate_scenarios:
        _step(f"  → Scenario: {scenario}", "")

        fin_q = simulate_financials_quarterly(
            borrowers, macro_m, quarters,
            rng=np.random.default_rng(SEEDS["financials"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Financials", f"{len(fin_q):,} rows")
        _append("borrower_financials_q", fin_q)

        ops_m = simulate_operations_monthly(
            borrowers, macro_m, months,
            rng=np.random.default_rng(SEEDS["operations"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Operations", f"{len(ops_m):,} rows")
        _append("borrower_operations_m", ops_m)

        res_q = simulate_reserves_quarterly(
            borrowers, ops_m, fin_q, quarters,
            rng=np.random.default_rng(SEEDS["reserves"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Reserves", f"{len(res_q):,} rows")
        if len(res_q) > 0:
            _append("reserves_q", res_q)

        hedges = simulate_hedges_monthly(
            borrowers, ops_m, macro_m, months,
            rng=np.random.default_rng(SEEDS["hedges"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Hedges", f"{len(hedges):,} rows")
        if len(hedges) > 0:
            _append("hedge_position_m", hedges)
        # ops_m no longer needed after hedges — free it
        del ops_m
        gc.collect()

        # ── Trade credit book (commercial AR / receivables) ───────────────────
        trade_credit = simulate_trade_credit_monthly(
            counterparties, macro_m, months,
            rng=np.random.default_rng(SEEDS["snapshots"] + hash(scenario) % 10_000 + 1),
            scenario_id=scenario,
        )
        _step(f"    Trade credit", f"{len(trade_credit):,} rows  "
              f"holds={trade_credit['credit_hold_flag'].sum() if len(trade_credit) > 0 else 0}")
        if len(trade_credit) > 0:
            _append("trade_credit_terms_m", trade_credit)
        del trade_credit
        gc.collect()

        # ── Trading counterparty book (MTM, PFE, netting, CSA) ───────────────
        trading_exp = simulate_trading_exposure_monthly(
            counterparties, macro_m, months,
            rng=np.random.default_rng(SEEDS["snapshots"] + hash(scenario) % 10_000 + 2),
            scenario_id=scenario,
        )
        _step(f"    Trading exposure", f"{len(trading_exp):,} rows  "
              f"breaches={trading_exp['limit_breach_flag'].sum() if len(trading_exp) > 0 else 0}")
        if len(trading_exp) > 0:
            _append("trading_exposure_m", trading_exp)
        del trading_exp
        gc.collect()

        snaps = build_facility_snapshots(
            facilities, borrowers, fin_q, res_q, macro_m, months,
            rng=np.random.default_rng(SEEDS["snapshots"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Snapshots", f"{len(snaps):,} rows")
        _append("facility_snapshot_m", snaps)

        cov = test_covenants(
            facilities, covenant_defs, fin_q, snaps, quarters,
            rng=np.random.default_rng(SEEDS["covenants"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Covenants",
              f"{len(cov):,} rows  breaches={cov['breach_flag'].sum() if len(cov) > 0 else 0}")
        if len(cov) > 0:
            _append("covenant_test_fact", cov)

        # Ratings needs fin_q; snapshot baseline BEFORE freeing
        ratings = update_ratings(
            borrowers, fin_q, cov, macro_m, months, quarters,
            rng=np.random.default_rng(SEEDS["ratings"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Ratings", f"{len(ratings):,} rows")
        _append("rating_history_m", ratings)

        # Snapshot baseline data before any frees
        if scenario == "baseline":
            baseline_fin_q   = fin_q.copy()
            baseline_ratings = ratings.copy()
            baseline_cov     = cov.copy() if len(cov) > 0 else pd.DataFrame()

        del fin_q       # no longer needed after ratings
        gc.collect()

        defaults = simulate_defaults(
            borrowers, ratings, snaps, cov, months,
            rng=np.random.default_rng(SEEDS["defaults"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Defaults",
              f"{len(defaults):,} rows  "
              f"events={defaults['default_id'].nunique() if len(defaults) > 0 else 0}")
        if len(defaults) > 0:
            _append("default_event_fact", defaults)
        del cov, ratings    # no longer needed after defaults
        gc.collect()

        recoveries = simulate_recoveries(
            defaults, facilities, borrowers, snaps, res_q, macro_m, months,
            rng=np.random.default_rng(SEEDS["recoveries"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    Recoveries", f"{len(recoveries):,} rows")
        if len(recoveries) > 0:
            _append("recovery_cashflow_fact", recoveries)

        # Snapshot remaining baseline data before freeing
        if scenario == "baseline":
            baseline_res_q      = res_q.copy()
            baseline_hedges     = hedges.copy()
            baseline_snaps      = snaps.copy()
            baseline_defaults   = defaults.copy()   if len(defaults) > 0   else pd.DataFrame()
            baseline_recoveries = recoveries.copy() if len(recoveries) > 0 else pd.DataFrame()

        # Free remaining scenario data
        del res_q, hedges, snaps, defaults, recoveries
        gc.collect()

    # Close all streaming writers
    for w in writers.values():
        w.close()
    writers.clear()
    _step("All scenarios written", "")

    # ── 14. Noise injection (baseline only) ──────────────────────────────────
    # Read baseline ops_m back from parquet (freed earlier to save memory)
    ops_parquet = out_dir / "borrower_operations_m.parquet"
    if ops_parquet.exists():
        baseline_ops_m = pd.read_parquet(
            ops_parquet,
            filters=[("scenario_id", "=", "baseline")],
        )
    else:
        baseline_ops_m = pd.DataFrame()

    noisy = inject_noise(
        borrowers, facilities,
        baseline_fin_q, baseline_ops_m, baseline_res_q,
        baseline_hedges, baseline_snaps, baseline_ratings,
        rng=np.random.default_rng(SEEDS["dq_noise"]),
    )
    _step("Noise injection", "applied to baseline slices")
    del baseline_ops_m
    gc.collect()

    # ── 15. Validation ────────────────────────────────────────────────────────
    val_result = validate_all(
        borrowers=borrowers,
        facilities=facilities,
        fin_q=baseline_fin_q,
        ops_m=pd.DataFrame(),      # not needed for current validation checks
        reserves_q=baseline_res_q,
        snapshots=baseline_snaps,
        ratings_m=baseline_ratings,
        defaults=baseline_defaults,
        recoveries=baseline_recoveries,
        cov_tests=baseline_cov,
        macro_m=macro_m,
        scenario_id="baseline",
    )
    print(val_result.summary())

    # ── 16. Write static tables ───────────────────────────────────────────────
    static = {
        "borrower_dim":           borrowers,
        "counterparty_dim":       counterparties,
        "facility_dim":           facilities,
        "covenant_def_dim":       covenant_defs,
        "macro_scenario_m":       macro_m,
        "transaction_fact":       noisy["transaction_fact"],
    }
    for name, df in static.items():
        if len(df) == 0:
            continue
        path = out_dir / f"{name}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        mb = path.stat().st_size / 1e6
        _step(f"  Wrote {name}", f"{len(df):>10,} rows  {mb:.1f} MB  → {path}")

    # Report on streamed tables
    for name in [
        "borrower_financials_q", "borrower_operations_m", "reserves_q",
        "hedge_position_m", "facility_snapshot_m", "covenant_test_fact",
        "rating_history_m", "default_event_fact", "recovery_cashflow_fact",
        "trade_credit_terms_m", "trading_exposure_m",
    ]:
        path = out_dir / f"{name}.parquet"
        if path.exists():
            mb = path.stat().st_size / 1e6
            pf = pq.read_metadata(str(path))
            nrows = pf.num_rows
            _step(f"  Wrote {name}", f"{nrows:>10,} rows  {mb:.1f} MB  → {path}")

    elapsed = time.time() - t0
    _step("Done", f"elapsed={elapsed:.1f}s  output_dir={out_dir.resolve()}")

    # Return baseline tables for interactive use
    return {
        "borrower_dim":          borrowers,
        "counterparty_dim":      counterparties,
        "facility_dim":          facilities,
        "covenant_def_dim":      covenant_defs,
        "macro_scenario_m":      macro_m,
        "borrower_financials_q": baseline_fin_q,
        "reserves_q":            baseline_res_q,
        "hedge_position_m":      baseline_hedges,
        "facility_snapshot_m":   baseline_snaps,
        "covenant_test_fact":    baseline_cov,
        "rating_history_m":      baseline_ratings,
        "default_event_fact":    baseline_defaults,
        "recovery_cashflow_fact":baseline_recoveries,
        "transaction_fact":      noisy["transaction_fact"],
    }


def _step(label: str, detail: str):
    msg = f"{label:<40}  {detail}"
    log.info(msg)
    print(msg)
