"""Backfill MIMO OTA seed rows to the new MIMO_OTA test_type + full schema.

The DB likely already has rows from an earlier seed run with:
  test_type='MIMO', template_category='MIMO OTA 吞吐量',
  configuration = sparse 4-field JSON.

This script upgrades each such row in place:
  test_type           -> 'MIMO_OTA'
  configuration       -> full MIMOOTAConfiguration JSON (via legacy_to_mimo_ota_config)
  pass_criteria       -> mirror of configuration.pass_criteria
  lab_profile_id      -> active LabProfile.id if not already set

Idempotent: rows already on test_type='MIMO_OTA' are skipped.

Usage:
    cd api-service
    .venv/bin/python scripts/migrate_seed_mimo_ota.py
"""
import logging
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm.attributes import flag_modified

from app.db.database import SessionLocal
from app.models.lab_profile import LabProfile
from app.models.test_plan import TestCase
from app.schemas.mimo_ota.config import MIMO_OTA_TEST_TYPE
from app.services.mimo_ota.legacy_migration import legacy_to_mimo_ota_config

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migrate_seed_mimo_ota")

LEGACY_TEST_TYPE = "MIMO"
MIMO_OTA_CATEGORY = "MIMO OTA 吞吐量"


def main() -> int:
    db = SessionLocal()
    try:
        rows = (
            db.query(TestCase)
            .filter(
                TestCase.template_category == MIMO_OTA_CATEGORY,
                TestCase.is_template.is_(True),
            )
            .all()
        )
        if not rows:
            logger.info("No template rows in 'MIMO OTA 吞吐量' category — nothing to do.")
            return 0

        active_profile = (
            db.query(LabProfile).filter(LabProfile.is_active.is_(True)).first()
        )
        if not active_profile:
            logger.warning(
                "No active LabProfile — rows will be upgraded but lab_profile_id "
                "will stay NULL. Run scripts/seed_caict_lab_profile.py first to "
                "get full integration."
            )

        upgraded = 0
        skipped = 0
        for row in rows:
            if row.test_type == MIMO_OTA_TEST_TYPE and row.lab_profile_id is not None:
                logger.info("[skip] %s already on MIMO_OTA + bound (id=%s)", row.name, row.id)
                skipped += 1
                continue

            # Reconstruct a legacy-shaped dict from the row to feed the converter
            legacy_view = {
                "channel_model": row.channel_model,
                "channel_parameters": row.channel_parameters or {},
                "configuration": row.configuration or {},
                "pass_criteria": row.pass_criteria or {},
                "frequency_mhz": row.frequency_mhz,
                "bandwidth_mhz": row.bandwidth_mhz,
            }
            new_cfg = legacy_to_mimo_ota_config(legacy_view)

            row.test_type = MIMO_OTA_TEST_TYPE
            row.configuration = new_cfg
            row.pass_criteria = new_cfg["pass_criteria"]
            if row.lab_profile_id is None and active_profile is not None:
                row.lab_profile_id = active_profile.id

            # JSON columns need explicit dirty-flag for SQLAlchemy
            flag_modified(row, "configuration")
            flag_modified(row, "pass_criteria")

            logger.info(
                "[ok]   %s -> test_type=MIMO_OTA, %d cfg fields, lab_profile_id=%s",
                row.name,
                len(new_cfg),
                row.lab_profile_id,
            )
            upgraded += 1

        db.commit()
        logger.info(
            "\nBackfill summary: %d upgraded, %d already-current",
            upgraded,
            skipped,
        )
        return 0

    except Exception as e:
        logger.exception("Backfill failed: %s", e)
        db.rollback()
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
