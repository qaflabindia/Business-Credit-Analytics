"""
O&G business AR analytics pipeline.

Produces three tables per run:
  customer_dim          — static customer master
  macro_scenario_m      — monthly macro/commodity paths per scenario
  trade_credit_terms_m  — monthly AR ageing + credit terms per customer per scenario
"""
from __future__ import annotations
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .config import Config, SEEDS
from .generators.calendar    import make_calendar
from .generators.macro       import generate_macro_paths
from .generators.counterparties import generate_customers
from .generators.trade_credit   import simulate_trade_credit_monthly
from .noise       import inject_noise
from .validation  import validate_all

log = logging.getLogger(__name__)


def run(cfg: Config | None = None, verbose: bool = True) -> dict[str, pd.DataFrame]:
    """Execute the AR pipeline and return all tables as a dict."""
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
          f"scale={cfg.scale}  customers={cfg.n_customers}  "
          f"months={cfg.n_months}  scenarios={cfg.generate_scenarios}")

    # ── 1. Calendar ───────────────────────────────────────────────────────────
    months, _ = make_calendar(cfg.start_date, cfg.n_months)
    _step("Calendar", f"{len(months)} months")

    # ── 2. Macro ──────────────────────────────────────────────────────────────
    macro_m = generate_macro_paths(
        cfg.n_months, months,
        rng=np.random.default_rng(SEEDS["macro"]),
        scenarios=cfg.generate_scenarios,
    )
    _step("Macro", f"{len(macro_m):,} rows  scenarios={macro_m['scenario_id'].nunique()}")

    # ── 3. Customers ──────────────────────────────────────────────────────────
    customers = generate_customers(
        cfg.n_customers,
        rng=np.random.default_rng(SEEDS["customers"]),
    )
    _step("Customers",
          f"{len(customers):,} rows  "
          f"types={customers['customer_type'].value_counts().to_dict()}")

    # ── 4. AR (per scenario, streamed to parquet) ─────────────────────────────
    writers: dict[str, pq.ParquetWriter] = {}

    def _append(name: str, df: pd.DataFrame):
        if len(df) == 0:
            return
        table = pa.Table.from_pandas(df, preserve_index=False)
        if name not in writers:
            path = out_dir / f"{name}.parquet"
            writers[name] = pq.ParquetWriter(str(path), table.schema)
        writers[name].write_table(table)

    baseline_ar: pd.DataFrame | None = None

    for scenario in cfg.generate_scenarios:
        _step(f"  → Scenario: {scenario}", "")

        ar = simulate_trade_credit_monthly(
            customers, macro_m, months,
            rng=np.random.default_rng(SEEDS["trade_credit"] + hash(scenario) % 10_000),
            scenario_id=scenario,
        )
        _step(f"    AR", f"{len(ar):,} rows  "
              f"holds={ar['credit_hold_flag'].sum() if len(ar) > 0 else 0}")
        _append("trade_credit_terms_m", ar)

        if scenario == "baseline":
            baseline_ar = ar.copy()

    for w in writers.values():
        w.close()
    writers.clear()
    _step("All scenarios written", "")

    # ── 5. Noise injection (baseline slice only) ──────────────────────────────
    if baseline_ar is not None:
        baseline_ar = inject_noise(baseline_ar, customers,
                                   rng=np.random.default_rng(SEEDS["dq_noise"]))
        _step("Noise injection", "applied to baseline AR slice")

    # ── 6. Validation ─────────────────────────────────────────────────────────
    if baseline_ar is not None:
        val = validate_all(customers=customers, ar_m=baseline_ar, macro_m=macro_m)
        print(val.summary())

    # ── 7. Write static tables ────────────────────────────────────────────────
    static = {
        "customer_dim":      customers,
        "macro_scenario_m":  macro_m,
    }
    for name, df in static.items():
        if len(df) == 0:
            continue
        path = out_dir / f"{name}.parquet"
        df.to_parquet(path, index=False, engine="pyarrow")
        mb = path.stat().st_size / 1e6
        _step(f"  Wrote {name}", f"{len(df):>10,} rows  {mb:.1f} MB  → {path}")

    for name in ["trade_credit_terms_m"]:
        path = out_dir / f"{name}.parquet"
        if path.exists():
            mb = path.stat().st_size / 1e6
            pf = pq.read_metadata(str(path))
            nrows = pf.num_rows
            _step(f"  Wrote {name}", f"{nrows:>10,} rows  {mb:.1f} MB  → {path}")

    elapsed = time.time() - t0
    _step("Done", f"elapsed={elapsed:.1f}s  output_dir={out_dir.resolve()}")

    return {
        "customer_dim":         customers,
        "macro_scenario_m":     macro_m,
        "trade_credit_terms_m": baseline_ar if baseline_ar is not None else pd.DataFrame(),
    }


def _step(label: str, detail: str):
    msg = f"{label:<40}  {detail}"
    log.info(msg)
    print(msg)
