#!/usr/bin/env python
"""Run Alembic against the app or an analytics database.

Alembic resolves revision folders before ``env.py`` runs, so ``-x target=…`` alone
cannot switch version trees. This wrapper sets ``version_locations`` first.

Usage
-----
    python scripts/migrate.py app upgrade head
    python scripts/migrate.py automotive upgrade head
    python scripts/migrate.py automotive history
    python scripts/migrate.py insurance upgrade head
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from alembic import command
from alembic.config import Config

API_ROOT = Path(__file__).resolve().parents[1] / "apps" / "api"
MIGRATIONS_ROOT = API_ROOT / "migrations"
TARGETS = ("app", "automotive", "insurance")


def _config_for(target: str) -> Config:
    cfg = Config(str(API_ROOT / "alembic.ini"))
    if target == "app":
        locations = [str(MIGRATIONS_ROOT / "versions")]
    else:
        locations = [str(MIGRATIONS_ROOT / target / "versions")]
    cfg.set_main_option("version_locations", os.pathsep.join(locations))
    # env.py reads -x target=… for the database URL and metadata choice.
    cfg.cmd_opts = SimpleNamespace(x=[f"target={target}"], raiseerr=False)
    return cfg


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", choices=TARGETS)
    parser.add_argument(
        "alembic_args",
        nargs=argparse.REMAINDER,
        help="Alembic subcommand and args, e.g. upgrade head",
    )
    args = parser.parse_args()
    alembic_args = list(args.alembic_args)
    if alembic_args and alembic_args[0] == "--":
        alembic_args = alembic_args[1:]
    if not alembic_args:
        raise SystemExit("Missing Alembic command. Example: upgrade head")

    os.chdir(API_ROOT)
    if str(API_ROOT) not in sys.path:
        sys.path.insert(0, str(API_ROOT))

    cfg = _config_for(args.target)
    sub = alembic_args[0]
    rest = alembic_args[1:]

    if sub == "upgrade":
        command.upgrade(cfg, rest[0] if rest else "head")
    elif sub == "downgrade":
        command.downgrade(cfg, rest[0] if rest else "-1")
    elif sub == "history":
        command.history(cfg)
    elif sub == "current":
        command.current(cfg)
    elif sub == "heads":
        command.heads(cfg)
    elif sub == "stamp":
        command.stamp(cfg, rest[0] if rest else "head")
    else:
        raise SystemExit(
            f"Unsupported alembic command {sub!r}. "
            "Use upgrade, downgrade, history, current, heads, or stamp."
        )


if __name__ == "__main__":
    main()
