"""Database bootstrap — seed canonical out-of-the-box reference data.

# Why this exists

Production deployments need a reproducible "factory defaults" step that
runs once on first boot (and a no-op on every subsequent boot). Alembic
manages schema evolution; bootstrap manages *default rows*. Keeping the
two concerns separate means:

- Editing a default doesn't mutate the migration history.
- Re-running bootstrap is always safe — each seeder's idempotency rule
  decides whether to insert, update, or skip.
- A site can opt out of any individual seeder by simply not calling it.

# Adding a new seeder

1. Create ``app/services/bootstrap/<name>.py`` exporting a ``Seeder``
   instance (see ``chamber_presets.py`` for the reference shape).
2. Append it to ``ALL_SEEDERS`` below in dependency order — seeders run
   sequentially, so a seeder may depend on rows created by an earlier
   seeder.
3. Bump the seeder's ``version`` field whenever you change what default
   data it produces. Existing installations will detect the version
   mismatch on the next bootstrap run and re-execute the seeder.

# Running

::

    cd api-service
    python -m scripts.bootstrap          # apply pending seeders
    python -m scripts.bootstrap --dry-run  # report only, no writes
    python -m scripts.bootstrap --force    # rerun even if up-to-date
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable, List

from sqlalchemy.orm import Session

from app.models.bootstrap_history import BootstrapHistory

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SeedResult:
    """What a single seeder reports back to the bootstrap runner."""
    inserted: int
    skipped: int
    updated: int = 0


@dataclass(frozen=True)
class Seeder:
    """One unit of default-data seeding.

    ``run`` MUST be idempotent: running it twice on the same DB must
    produce the same end state. Concretely, that means each seeder
    looks up by a stable natural key (e.g. preset_type + canonical
    name) and inserts only if the row is absent.
    """
    name: str             # Stable identifier; persisted to bootstrap_history
    version: int          # Bump when default data changes
    description: str      # One-liner shown in the CLI report
    run: Callable[[Session], SeedResult]


def run_all(
    db: Session,
    seeders: List[Seeder],
    *,
    force: bool = False,
    dry_run: bool = False,
) -> List[tuple[Seeder, SeedResult | None, str]]:
    """Run each seeder in order, respecting bootstrap_history.

    Returns a list of ``(seeder, result, status)`` triples for the CLI
    to render. ``status`` is one of "ran", "skipped (up-to-date)",
    "skipped (dry-run)", "failed".
    """
    report: List[tuple[Seeder, SeedResult | None, str]] = []

    for seeder in seeders:
        history = (
            db.query(BootstrapHistory)
            .filter(BootstrapHistory.seeder_name == seeder.name)
            .first()
        )
        is_up_to_date = (
            history is not None
            and history.seeder_version >= seeder.version
        )
        if is_up_to_date and not force:
            report.append((seeder, None, "skipped (up-to-date)"))
            logger.info(
                "[bootstrap] %s v%d — up-to-date, skip",
                seeder.name, seeder.version,
            )
            continue

        if dry_run:
            report.append((seeder, None, "skipped (dry-run)"))
            logger.info(
                "[bootstrap] %s v%d — would run (dry-run)",
                seeder.name, seeder.version,
            )
            continue

        try:
            result = seeder.run(db)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception("[bootstrap] %s FAILED: %s", seeder.name, exc)
            report.append((seeder, None, f"failed: {exc}"))
            # Continue with subsequent seeders rather than aborting the
            # whole bootstrap — failures of one seeder shouldn't block
            # unrelated ones (and the operator still gets a full report).
            continue

        if history is None:
            db.add(BootstrapHistory(
                seeder_name=seeder.name,
                seeder_version=seeder.version,
                rows_inserted=result.inserted,
                rows_skipped=result.skipped,
            ))
        else:
            history.seeder_version = seeder.version
            history.rows_inserted = result.inserted
            history.rows_skipped = result.skipped

        db.commit()
        logger.info(
            "[bootstrap] %s v%d — ran, +%d / =%d",
            seeder.name, seeder.version, result.inserted, result.skipped,
        )
        report.append((seeder, result, "ran"))

    return report


# Registered seeders, in dependency order. Each seeder is idempotent on
# its natural key, so re-running ``bootstrap`` produces no duplicates.
# Order matters when a later seeder references rows an earlier one
# creates — ``probes`` looks up the Type-C chamber preset by FK, so
# ``chamber_presets`` must run first. The remaining seeders are
# independent and could in principle run in any order, but a stable
# order makes the bootstrap report easier to scan.
from app.services.bootstrap.chamber_presets import chamber_presets_seeder
from app.services.bootstrap.instruments import instruments_seeder
from app.services.bootstrap.probes import probes_seeder
from app.services.bootstrap.report_templates import report_templates_seeder
from app.services.bootstrap.sequences import sequences_seeder
from app.services.bootstrap.test_case_templates import test_case_templates_seeder

ALL_SEEDERS: List[Seeder] = [
    chamber_presets_seeder,
    probes_seeder,
    instruments_seeder,
    sequences_seeder,
    report_templates_seeder,
    test_case_templates_seeder,
]
