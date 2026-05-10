"""Bootstrap CLI — apply default seed data to the configured database.

Run this once on first deploy and any time a seeder version is bumped.
Idempotent: re-running on an already-seeded DB is a no-op.

Usage::

    cd api-service
    python -m scripts.bootstrap
    python -m scripts.bootstrap --dry-run    # plan only, no writes
    python -m scripts.bootstrap --force      # rerun even if up-to-date
    python -m scripts.bootstrap --only chamber_presets    # one seeder

Exit codes:
    0  all seeders applied or skipped cleanly
    1  one or more seeders raised an error
"""
from __future__ import annotations

import argparse
import logging
import sys

from app.db.database import SessionLocal
from app.services.bootstrap import ALL_SEEDERS, run_all


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report what would run without writing to the DB",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Rerun seeders even if their version matches bootstrap_history",
    )
    parser.add_argument(
        "--only", action="append", metavar="SEEDER_NAME",
        help="Only run the named seeder(s); may be passed multiple times",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    selected = ALL_SEEDERS
    if args.only:
        unknown = set(args.only) - {s.name for s in ALL_SEEDERS}
        if unknown:
            print(f"ERROR: unknown seeder(s): {', '.join(sorted(unknown))}",
                  file=sys.stderr)
            print(f"Available: {', '.join(s.name for s in ALL_SEEDERS)}",
                  file=sys.stderr)
            return 1
        selected = [s for s in ALL_SEEDERS if s.name in args.only]

    db = SessionLocal()
    try:
        report = run_all(db, selected, force=args.force, dry_run=args.dry_run)
    finally:
        db.close()

    print()
    print("Bootstrap report")
    print("=" * 72)
    any_failed = False
    for seeder, result, status in report:
        line = f"  {seeder.name:30s} v{seeder.version}  {status}"
        if result is not None:
            line += f"  (+{result.inserted} new, ={result.skipped} kept)"
        print(line)
        if status.startswith("failed"):
            any_failed = True
    print("=" * 72)
    return 1 if any_failed else 0


if __name__ == "__main__":
    sys.exit(main())
