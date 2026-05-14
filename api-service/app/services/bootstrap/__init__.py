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


# ---------------------------------------------------------------------------
# Lifespan wrapper
# ---------------------------------------------------------------------------
#
# P0-1 (first-call roadmap): the FastAPI lifespan calls this once at startup
# so a fresh deploy is never "empty DB + no chambers + no instruments + no
# templates". Operators stop needing to run `python -m scripts.bootstrap`
# manually as a deploy step.
#
# This is a *wrapper*, not a re-implementation, so the manual CLI and the
# auto-on-startup path go through the same `run_all` + `bootstrap_history`
# logic. Idempotent: re-running the app on an already-seeded DB is a no-op
# (each seeder's history row pins its applied version).

# Stable 64-bit key for the PG advisory lock that serializes startup
# bootstrap across concurrent workers. Arbitrary value picked once and
# kept constant — changing it would let two app generations seed in
# parallel during a rolling deploy.
_PG_BOOTSTRAP_LOCK_KEY = 0x7E7C_B007_57AB_1ED1


def run_bootstrap_on_startup(session_factory: Callable[[], Session]) -> bool:
    """Run all registered seeders against a session opened from
    ``session_factory`` (typically ``app.db.database.SessionLocal``).

    Returns True if all seeders succeeded (including "skipped (up-to-date)"
    paths), False if any seeder failed. Failure of one seeder does not
    abort the others — see ``run_all`` — but the caller may want to log
    a louder warning, so we surface the aggregate result.

    # Concurrent-worker safety (Codex P1 on #17)

    Production runs the API as ``gunicorn --workers 4`` — every worker
    enters the FastAPI lifespan concurrently and reaches this function
    against the same shared DB. Without serialization, two workers can
    both observe an empty ``bootstrap_history`` and both insert factory
    defaults; the chamber-preset natural key has no unique constraint,
    so duplicates land silently.

    The fix is a Postgres advisory lock held for the lifetime of this
    session: the first worker acquires it and seeds; the others block
    until release, then proceed and find ``bootstrap_history`` already
    populated (so all seeders short-circuit as "up-to-date"). We use a
    *session-level* lock — not ``pg_advisory_xact_lock`` — because
    ``run_all`` commits once per seeder, and an xact lock would release
    mid-bootstrap, reopening the race for seeders 2..N.

    SQLite (tests) has no advisory locks. Tests run single-threaded so
    the race doesn't exist there; we silently skip the lock for any
    non-Postgres dialect rather than emulating it.

    The function logs a formatted ``BOOTSTRAP REPORT`` block at INFO
    level so operators can confirm what was seeded without grepping
    mixed startup output. Format mirrors ``HAL READINESS REPORT``.
    """
    db = session_factory()
    lock_acquired = False
    try:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            from sqlalchemy import text
            db.execute(
                text("SELECT pg_advisory_lock(:key)"),
                {"key": _PG_BOOTSTRAP_LOCK_KEY},
            )
            lock_acquired = True
            logger.info(
                "[bootstrap] acquired PG advisory lock %s — serialising "
                "concurrent worker startup",
                hex(_PG_BOOTSTRAP_LOCK_KEY),
            )
        report = run_all(db, ALL_SEEDERS)
    finally:
        if lock_acquired:
            try:
                from sqlalchemy import text
                db.execute(
                    text("SELECT pg_advisory_unlock(:key)"),
                    {"key": _PG_BOOTSTRAP_LOCK_KEY},
                )
                db.commit()  # ensure unlock is flushed before close
            except Exception as exc:  # noqa: BLE001
                # Connection close releases session-level locks anyway,
                # so a failed explicit unlock isn't fatal — just noisy.
                logger.warning(
                    "[bootstrap] explicit advisory unlock failed: %s "
                    "(lock will be released on connection close)", exc,
                )
        db.close()

    _log_bootstrap_report(report)
    return not any(status.startswith("failed") for _, _, status in report)


def _log_bootstrap_report(
    report: List[tuple[Seeder, SeedResult | None, str]],
) -> None:
    """Print a formatted bootstrap summary alongside the HAL readiness
    block so operators see seed status in the same place.

    Example output (printed via ``logger.info`` so it lands in the same
    log stream + log file as the rest of startup)::

        ═══════ BOOTSTRAP REPORT ═══════
        ✓ chamber_presets        v1   ran                    +4 new / =0 kept
        ○ probes                 v1   skipped (up-to-date)
        ✓ instruments            v2   ran                    +12 new / =0 kept
        ✗ sequences              v1   failed: ...
        ═════════════════════════════════
        6 seeders · +16 new · =0 kept · 1 failed
    """
    if not report:
        logger.info("[bootstrap] no seeders registered")
        return

    icons = {"ran": "✓", "failed": "✗"}  # "skipped" → ○ via default below

    name_w = max(len(s.name) for s, _, _ in report)
    name_w = max(name_w, len("seeder"))
    status_w = max(len(status) for _, _, status in report)
    status_w = max(status_w, len("status"))

    header_label = "═" * 19 + " BOOTSTRAP REPORT " + "═" * 19
    lines = [header_label]
    total_inserted = 0
    total_skipped_rows = 0
    ran = failed = up_to_date = 0
    for seeder, result, status in report:
        icon = icons.get(status, "○") if not status.startswith("failed") else "✗"
        detail = ""
        if result is not None:
            detail = f"+{result.inserted} new / ={result.skipped} kept"
            total_inserted += result.inserted
            total_skipped_rows += result.skipped
        lines.append(
            f"{icon} {seeder.name:<{name_w}}  v{seeder.version}  "
            f"{status:<{status_w}}  {detail}"
        )
        if status == "ran":
            ran += 1
        elif status.startswith("failed"):
            failed += 1
        else:
            up_to_date += 1
    lines.append("═" * len(header_label))
    lines.append(
        f"{len(report)} seeders · +{total_inserted} new · "
        f"={total_skipped_rows} kept · {failed} failed"
    )
    for line in lines:
        logger.info("[bootstrap] %s", line)
