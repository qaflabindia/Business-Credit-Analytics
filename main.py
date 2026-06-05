"""
Credit Analytics — Synthetic Oil & Gas Credit Portfolio Generator
Entry point.

Usage:
  python main.py                     # standard scale (4 000 borrowers, 120 months)
  python main.py --scale lite        # lite scale  (1 000 borrowers, 36 months)
  python main.py --scale research    # research scale (15 000 borrowers, 180 months)
  python main.py --scenarios baseline severe_demand   # subset of scenarios
  python main.py --out ./my_data     # custom output directory
"""
import argparse
import sys
from pathlib import Path

# Ensure the package is importable when run from the project root
sys.path.insert(0, str(Path(__file__).parent))

from credit_analytics.config import Config
from credit_analytics.pipeline import run


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Generate a synthetic oil & gas credit analytics dataset"
    )
    p.add_argument(
        "--scale",
        choices=["lite", "standard", "research"],
        default="standard",
        help="Dataset scale (default: standard)",
    )
    p.add_argument(
        "--scenarios",
        nargs="+",
        choices=["baseline", "severe_demand", "geopolitical_supply", "disorderly_transition"],
        default=["baseline", "severe_demand", "geopolitical_supply", "disorderly_transition"],
        help="Which macro scenarios to generate (default: all four)",
    )
    p.add_argument(
        "--out",
        default="data_out",
        help="Output directory for parquet files (default: data_out/)",
    )
    p.add_argument(
        "--borrowers",
        type=int,
        default=None,
        help="Override number of borrowers (overrides --scale)",
    )
    p.add_argument(
        "--months",
        type=int,
        default=None,
        help="Override number of months (overrides --scale)",
    )
    return p.parse_args()


def main():
    args = _parse_args()

    # Build config
    if args.scale == "lite":
        cfg = Config.lite()
    elif args.scale == "research":
        cfg = Config.research()
    else:
        cfg = Config.standard()

    # Apply overrides
    if args.borrowers is not None:
        cfg.n_borrowers = args.borrowers
    if args.months is not None:
        cfg.n_months = args.months
    cfg.output_dir = args.out
    cfg.generate_scenarios = args.scenarios

    print("=" * 60)
    print("  Credit Analytics — Synthetic Dataset Generator")
    print("=" * 60)
    print(f"  Scale:       {cfg.scale}")
    print(f"  Borrowers:   {cfg.n_borrowers:,}")
    print(f"  Months:      {cfg.n_months}")
    print(f"  Quarters:    {cfg.n_quarters}")
    print(f"  Scenarios:   {', '.join(cfg.generate_scenarios)}")
    print(f"  Output dir:  {cfg.output_dir}")
    print("=" * 60)
    print()

    tables = run(cfg, verbose=True)

    print()
    print("=" * 60)
    print("  Generation complete. Tables written:")
    for name, df in tables.items():
        print(f"    {name:<35}  {len(df):>10,} rows")
    print("=" * 60)


if __name__ == "__main__":
    main()
