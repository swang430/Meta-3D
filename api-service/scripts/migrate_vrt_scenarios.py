"""One-time migration: custom_scenarios.json → test_cases table (VRT TestCases).

Phase 2.2 of the VRT-into-TestCase consolidation. Reads existing custom
scenarios from the legacy JSON file and persists each one as a TestCase row
with test_type='VirtualRoadTest'.

Idempotent: a scenario with a `legacy_id:<id>` tag already in the DB is
skipped. Renames the JSON file to .migrated upon successful completion so
the old loader does not pick it up again.

Usage:
    cd api-service
    .venv/bin/python scripts/migrate_vrt_scenarios.py
"""
import json
import logging
import os
import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.db.database import SessionLocal
from app.models.test_plan import TestCase
from app.schemas.road_test import VRT_TEST_TYPE
from app.schemas.road_test.execution import TestMode
from app.schemas.road_test.scenario import RoadTestScenario
from app.services.road_test.vrt_service import vrt_service

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("migrate_vrt")

JSON_PATH = Path(__file__).resolve().parent.parent / "data" / "custom_scenarios.json"


def _legacy_tag(legacy_id: str) -> str:
    return f"legacy_id:{legacy_id}"


def _has_legacy_id(db, legacy_id: str) -> bool:
    """Check if a TestCase row already carries the legacy_id tag."""
    rows = (
        db.query(TestCase)
        .filter(
            TestCase.test_type == VRT_TEST_TYPE,
            TestCase.tags.isnot(None),
        )
        .all()
    )
    target = _legacy_tag(legacy_id)
    return any(target in (tc.tags or []) for tc in rows)


def main() -> int:
    if not JSON_PATH.exists():
        logger.info("No %s — nothing to migrate.", JSON_PATH)
        return 0

    raw = json.loads(JSON_PATH.read_text())
    if not raw:
        logger.info("Empty scenario file — nothing to migrate.")
        return 0

    db = SessionLocal()
    migrated = 0
    skipped = 0
    failed = 0

    try:
        for legacy_id, payload in raw.items():
            if _has_legacy_id(db, legacy_id):
                logger.info("[skip] %s already migrated", legacy_id)
                skipped += 1
                continue

            try:
                scenario = RoadTestScenario.model_validate(payload)
                config = vrt_service.scenario_to_vrt_config(
                    scenario, mode=TestMode.DIGITAL_TWIN
                )
                tags = list(scenario.tags or [])
                tags.append(_legacy_tag(legacy_id))
                test_case = vrt_service.create_vrt_test_case(
                    db,
                    name=scenario.name,
                    configuration=config,
                    created_by=scenario.author or "migration",
                    description=scenario.description,
                    tags=tags,
                )
                logger.info(
                    "[ok]   %s → TestCase %s (%s)",
                    legacy_id,
                    test_case.id,
                    scenario.name,
                )
                migrated += 1
            except Exception as e:  # pragma: no cover - migration loop
                logger.error("[fail] %s: %s", legacy_id, e)
                failed += 1
    finally:
        db.close()

    logger.info(
        "\nMigration summary: %d migrated, %d already present, %d failed",
        migrated,
        skipped,
        failed,
    )

    if failed == 0 and migrated > 0:
        target = JSON_PATH.with_suffix(".json.migrated")
        os.rename(JSON_PATH, target)
        logger.info("Renamed %s → %s", JSON_PATH.name, target.name)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
