"""TestCase 服务层 —— ARCH-1 S4b 后本文件只剩 TestCaseService。

⚠️ 文件名 test_plan_service 自此名不副实, 与 api/test_plan.py 同因:
改名/改前缀是独立工单 (契约同步四步 + GUI 全量改调用), 不夹带进拆除片。
"""
from sqlalchemy.orm import Session
from typing import List, Optional
from uuid import UUID
import logging
from pydantic import ValidationError

from app.models.test_plan import TestCase
from app.schemas.mimo_ota.config import (
    MIMO_OTA_TEST_TYPE,
    canonicalize_mimo_ota_configuration_payload,
)

logger = logging.getLogger(__name__)


class MIMOOTACarrierTruthError(ValueError):
    """MIMO OTA 顶层镜像与 PCell 真值不一致或配置无效。"""


def _is_mimo_ota_test_type(test_type: object) -> bool:
    return getattr(test_type, "value", test_type) == MIMO_OTA_TEST_TYPE


def _canonicalize_test_case_configuration(
    test_type: object,
    configuration: dict,
) -> dict:
    if not _is_mimo_ota_test_type(test_type):
        return configuration
    try:
        return canonicalize_mimo_ota_configuration_payload(configuration)
    except ValidationError as exc:
        raise MIMOOTACarrierTruthError(str(exc)) from exc


# ARCH-1 S4b: 计划链拆除。原有 7 个 Service 类只留 TestCaseService ——
#   TestPlanService(700) / TestStepService(210) / TestQueueService(391) /
#   TestExecutionService(529) / TestSequenceService(57) 随各自的路由删;
#   StatisticsService(131) 是**死代码** —— api/report.py 用的是
#   services/statistics_service.py 里的同名类, 这个从来没人 import。
# 净删 2040 行。

class TestCaseService:
    """Service for managing test cases"""

    def create_test_case(
        self,
        db: Session,
        name: str,
        test_type: str,
        configuration: dict,
        created_by: str,
        **kwargs
    ) -> TestCase:
        """Create a new test case"""
        configuration = _canonicalize_test_case_configuration(
            test_type,
            configuration,
        )
        test_case = TestCase(
            name=name,
            test_type=test_type,
            configuration=configuration,
            created_by=created_by,
            **kwargs
        )

        db.add(test_case)
        db.commit()
        db.refresh(test_case)

        logger.info(f"Created test case: {test_case.id} - {name}")
        return test_case

    def get_test_case(self, db: Session, test_case_id: UUID) -> Optional[TestCase]:
        """Get a test case by ID"""
        return db.query(TestCase).filter(TestCase.id == test_case_id).first()

    def list_test_cases(
        self,
        db: Session,
        skip: int = 0,
        limit: int = 100,
        test_type: Optional[str] = None,
        is_template: Optional[bool] = None,
        template_category: Optional[str] = None
    ) -> List[TestCase]:
        """List test cases with filters"""
        query = db.query(TestCase)

        if test_type:
            query = query.filter(TestCase.test_type == test_type)
        if is_template is not None:
            query = query.filter(TestCase.is_template == is_template)
        if template_category:
            query = query.filter(TestCase.template_category == template_category)

        query = query.order_by(TestCase.created_at.desc())
        return query.offset(skip).limit(limit).all()

    def update_test_case(
        self,
        db: Session,
        test_case_id: UUID,
        **kwargs
    ) -> Optional[TestCase]:
        """Update a test case"""
        test_case = self.get_test_case(db, test_case_id)
        if not test_case:
            return None

        final_test_type = kwargs.get("test_type", test_case.test_type)
        configuration_supplied = (
            "configuration" in kwargs and kwargs["configuration"] is not None
        )
        retyped_to_mimo_ota = (
            _is_mimo_ota_test_type(final_test_type)
            and not _is_mimo_ota_test_type(test_case.test_type)
        )
        if configuration_supplied or retyped_to_mimo_ota:
            candidate_configuration = (
                kwargs["configuration"]
                if configuration_supplied
                else test_case.configuration
            )
            kwargs["configuration"] = _canonicalize_test_case_configuration(
                final_test_type,
                candidate_configuration,
            )

        for key, value in kwargs.items():
            # P2-24: PATCH {lab_profile_id: null} 是显式解除绑定，不是“字段未给”。
            # 其它存量字段继续保持原有 None-leaves-unchanged 语义。
            if (value is not None or key == "lab_profile_id") and hasattr(test_case, key):
                setattr(test_case, key, value)

        db.commit()
        db.refresh(test_case)

        logger.info(f"Updated test case: {test_case_id}")
        return test_case

    def delete_test_case(self, db: Session, test_case_id: UUID) -> bool:
        """Delete a test case"""
        test_case = self.get_test_case(db, test_case_id)
        if not test_case:
            return False

        db.delete(test_case)
        db.commit()

        logger.info(f"Deleted test case: {test_case_id}")
        return True
