"""Generate the realistic Indian automotive dataset as CSV files (no database needed).

Usage
-----
    # from askdb/
    python scripts/generate_india_auto_dataset.py                      # ~2.1M sales rows
    python scripts/generate_india_auto_dataset.py --rows 50000 --out data/india_auto_small
    python scripts/generate_india_auto_dataset.py --split-date 2026-06-30   # base + increment

Outputs (in ``--out``): one CSV per automotive table in load order, ``manifest.json``
(row counts, market share and EV share by year) and ``reference_model_calendar.csv``
(launch / discontinuation per carline). With ``--split-date`` rows introduced after the
date (new models, cities, dealers, salespeople and later sales) go to ``increment/`` so
the Entity Catalog can be demonstrated detecting new values.

Load with ``python scripts/load_india_auto_dataset.py --data-dir <out> --replace``.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.analytics.india_auto_generator import (  # noqa: E402
    DEFAULT_ROWS,
    DEFAULT_SEED,
    GeneratorConfig,
    IndiaAutoDatasetGenerator,
)

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "india_auto"


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--rows", type=int, default=DEFAULT_ROWS, help="target fact_sales rows")
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="random seed (deterministic)"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output directory")
    parser.add_argument(
        "--end-date",
        type=date.fromisoformat,
        default=date.today(),
        help="last sales date, YYYY-MM-DD (default today)",
    )
    parser.add_argument(
        "--split-date",
        type=date.fromisoformat,
        default=None,
        help="write rows introduced after this date to <out>/increment",
    )
    parser.add_argument("--forecast-horizon", type=int, default=6, help="future forecast months")
    args = parser.parse_args()
    if args.rows < 1000:
        raise SystemExit("--rows must be >= 1000")
    if args.split_date and not date(2015, 6, 30) < args.split_date < args.end_date:
        raise SystemExit("--split-date must fall between 2015-06-30 and --end-date")

    config = GeneratorConfig(
        rows=args.rows,
        seed=args.seed,
        end_date=args.end_date,
        split_date=args.split_date,
        forecast_horizon=args.forecast_horizon,
        progress=lambda message: print(message, flush=True),
    )
    report = IndiaAutoDatasetGenerator(config).generate(args.out)
    summary = report.to_dict()
    print(f"\nWrote CSVs to {args.out} in {summary['seconds']}s")
    for table, count in summary["counts"].items():
        extra = summary["increment_counts"].get(table)
        print(f"  {table:<24} {count:>12,}" + (f"  (+{extra:,} increment)" if extra else ""))
    latest = max(summary["yearly_make_share_pct"], default=None)
    if latest:
        top = list(summary["yearly_make_share_pct"][latest].items())[:5]
        print(f"\n{latest} market share: " + ", ".join(f"{m} {s}%" for m, s in top))
        print("EV share by year: " + json.dumps(summary["yearly_ev_share_pct"]))


if __name__ == "__main__":
    main()
