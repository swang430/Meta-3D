"""
VRT (Virtual Road Test) service.

Phase 1 of the VRT-into-TestCase consolidation. This service treats VRT
scenarios as `TestCase` rows with `test_type='VirtualRoadTest'`. It provides:

- CRUD over VRT TestCases (filtered queries on the `test_cases` table)
- Conversion between the legacy `RoadTestScenario` shape and the new
  `VirtualRoadTestConfig` (which lives inside `TestCase.configuration` JSON)

Phase 2 will route the existing /road-test/scenarios endpoints through this
service so VRT data persists in the database instead of in-memory dicts.
"""
from __future__ import annotations

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.test_plan import TestCase, TestCaseType
from app.schemas.road_test import (
    RoadTestScenario,
    ScenarioSource,
    TestMode,
    VRT_TEST_TYPE,
    VirtualRoadTestConfig,
)

logger = logging.getLogger(__name__)


class VRTService:
    """CRUD + scenario↔config conversion for VRT TestCases."""

    # ──────────────────────────────────────────────────────────────────────
    # Conversion helpers (pure, no DB)
    # ──────────────────────────────────────────────────────────────────────

    @staticmethod
    def scenario_to_vrt_config(
        scenario: RoadTestScenario,
        mode: TestMode = TestMode.DIGITAL_TWIN,
        topology_id: Optional[str] = None,
    ) -> VirtualRoadTestConfig:
        """Project a legacy RoadTestScenario onto the VirtualRoadTestConfig shape."""
        return VirtualRoadTestConfig(
            mode=mode,
            category=scenario.category,
            topology_id=topology_id,
            network=scenario.network,
            base_stations=scenario.base_stations,
            route=scenario.route,
            environment=scenario.environment,
            traffic=scenario.traffic,
            events=scenario.events,
            kpi_definitions=scenario.kpi_definitions,
            step_configuration=scenario.step_configuration,
        )

    @staticmethod
    def vrt_test_case_to_scenario(test_case: TestCase) -> RoadTestScenario:
        """Project a VRT TestCase row back onto the legacy RoadTestScenario shape.

        Used by backward-compat aliases (Phase 2) so existing /road-test/scenarios
        consumers keep receiving RoadTestScenario JSON while the underlying
        storage is `test_cases`.
        """
        if test_case.test_type != VRT_TEST_TYPE:
            raise ValueError(
                f"TestCase {test_case.id} is not a VirtualRoadTest "
                f"(test_type={test_case.test_type!r})"
            )
        config = VirtualRoadTestConfig.model_validate(test_case.configuration or {})
        return RoadTestScenario(
            id=str(test_case.id),
            name=test_case.name,
            category=config.category,
            source=ScenarioSource.CUSTOM,
            tags=test_case.tags or [],
            description=test_case.description,
            network=config.network,
            base_stations=config.base_stations,
            route=config.route,
            environment=config.environment,
            traffic=config.traffic,
            events=config.events,
            kpi_definitions=config.kpi_definitions,
            step_configuration=config.step_configuration,
            created_at=test_case.created_at,
            updated_at=test_case.updated_at,
            author=test_case.created_by,
            version=test_case.version or "1.0",
        )

    # ──────────────────────────────────────────────────────────────────────
    # CRUD over `test_cases` table, filtered to test_type='VirtualRoadTest'
    # ──────────────────────────────────────────────────────────────────────

    def create_vrt_test_case(
        self,
        db: Session,
        *,
        name: str,
        configuration: VirtualRoadTestConfig,
        created_by: str,
        description: Optional[str] = None,
        tags: Optional[List[str]] = None,
        is_template: bool = False,
        template_category: Optional[str] = None,
        # TestCase-level RF columns (kept on the table itself, not in configuration)
        frequency_mhz: Optional[float] = None,
        bandwidth_mhz: Optional[float] = None,
        channel_model: Optional[str] = None,
        tx_power_dbm: Optional[float] = None,
        test_duration_sec: Optional[float] = None,
        pass_criteria: Optional[dict] = None,
    ) -> TestCase:
        """Persist a VRT scenario as a TestCase row."""
        # Derive RF defaults from the VRT configuration when caller did not supply them.
        if bandwidth_mhz is None:
            bandwidth_mhz = configuration.network.bandwidth_mhz
        if test_duration_sec is None:
            test_duration_sec = configuration.route.duration_s
        if tx_power_dbm is None and configuration.base_stations:
            tx_power_dbm = configuration.base_stations[0].tx_power_dbm

        test_case = TestCase(
            name=name,
            description=description,
            test_type=TestCaseType.VIRTUAL_ROAD_TEST.value,
            configuration=configuration.model_dump(mode="json"),
            pass_criteria=pass_criteria,
            channel_model=channel_model,
            frequency_mhz=frequency_mhz,
            tx_power_dbm=tx_power_dbm,
            bandwidth_mhz=bandwidth_mhz,
            test_duration_sec=test_duration_sec,
            is_template=is_template,
            template_category=template_category,
            created_by=created_by,
            tags=tags or [],
        )
        db.add(test_case)
        db.commit()
        db.refresh(test_case)
        logger.info("Created VRT TestCase %s — %s", test_case.id, name)
        return test_case

    def get_vrt_test_case(self, db: Session, case_id: UUID) -> Optional[TestCase]:
        return (
            db.query(TestCase)
            .filter(
                TestCase.id == case_id,
                TestCase.test_type == VRT_TEST_TYPE,
            )
            .first()
        )

    def list_vrt_test_cases(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        is_template: Optional[bool] = None,
        template_category: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> List[TestCase]:
        query = db.query(TestCase).filter(TestCase.test_type == VRT_TEST_TYPE)
        if is_template is not None:
            query = query.filter(TestCase.is_template == is_template)
        if template_category is not None:
            query = query.filter(TestCase.template_category == template_category)
        if created_by is not None:
            query = query.filter(TestCase.created_by == created_by)
        return (
            query.order_by(TestCase.created_at.desc()).offset(skip).limit(limit).all()
        )

    def update_vrt_test_case(
        self,
        db: Session,
        case_id: UUID,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        configuration: Optional[VirtualRoadTestConfig] = None,
        tags: Optional[List[str]] = None,
        is_template: Optional[bool] = None,
        template_category: Optional[str] = None,
    ) -> Optional[TestCase]:
        test_case = self.get_vrt_test_case(db, case_id)
        if test_case is None:
            return None

        if name is not None:
            test_case.name = name
        if description is not None:
            test_case.description = description
        if configuration is not None:
            test_case.configuration = configuration.model_dump(mode="json")
            # Refresh derived RF columns when configuration changes.
            test_case.bandwidth_mhz = configuration.network.bandwidth_mhz
            test_case.test_duration_sec = configuration.route.duration_s
            if configuration.base_stations:
                test_case.tx_power_dbm = configuration.base_stations[0].tx_power_dbm
        if tags is not None:
            test_case.tags = tags
        if is_template is not None:
            test_case.is_template = is_template
        if template_category is not None:
            test_case.template_category = template_category

        db.commit()
        db.refresh(test_case)
        return test_case

    def delete_vrt_test_case(self, db: Session, case_id: UUID) -> bool:
        test_case = self.get_vrt_test_case(db, case_id)
        if test_case is None:
            return False
        db.delete(test_case)
        db.commit()
        logger.info("Deleted VRT TestCase %s", case_id)
        return True


vrt_service = VRTService()
