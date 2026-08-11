"""把正式执行的系统失败一次性发布到活动告警摘要。

调用方必须先提交 ``TestExecution.status='failed'``；本模块再用独立 session
best-effort 写告警。这样告警表故障不会把真实执行终态回滚成 running。
"""
from __future__ import annotations

import logging
from uuid import UUID

from app.db.database import SessionLocal
from app.models.alert import Alert, AlertSeverity, AlertStatus
from app.models.test_plan import TestExecution

logger = logging.getLogger(__name__)

EXECUTION_FAILED_ALERT_TYPE = "execution_failed"
FORMAL_EXECUTION_SOURCES = frozenset({"test_case_runner", "commissioning_api"})


def emit_execution_failed_alert(execution_id: UUID) -> bool:
    """为一个新进入 failed 的正式执行创建告警；重复/非正式调用返回 False。

    去重覆盖告警全部生命周期。操作员已 acknowledge/resolve/dismiss 的同一执行
    不得因调用方重试而重新变成 active。
    """
    db = SessionLocal()
    try:
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == execution_id)
            .first()
        )
        if (
            execution is None
            or execution.status != "failed"
            or execution.executed_by not in FORMAL_EXECUTION_SOURCES
        ):
            return False

        existing = (
            db.query(Alert.id)
            .filter(
                Alert.alert_type == EXECUTION_FAILED_ALERT_TYPE,
                Alert.related_entity_type == "test_execution",
                Alert.related_entity_id == execution.id,
            )
            .first()
        )
        if existing is not None:
            return False

        config = execution.config or {}
        reason = execution.error_message or config.get("error_message")
        message = f"执行 {execution.id} 已失败"
        if reason:
            message += f"：{reason}"

        db.add(Alert(
            title="正式测试执行失败",
            message=message,
            severity=AlertSeverity.ERROR.value,
            alert_type=EXECUTION_FAILED_ALERT_TYPE,
            source=execution.executed_by,
            status=AlertStatus.ACTIVE.value,
            related_entity_type="test_execution",
            related_entity_id=execution.id,
            created_by=execution.executed_by,
        ))
        db.commit()
        logger.info("已发布执行失败告警: execution=%s", execution.id)
        return True
    except Exception:  # noqa: BLE001 - 告警失败不得改写真实执行终态
        db.rollback()
        logger.exception("执行 %s 的失败告警写入失败（执行终态保持 failed）", execution_id)
        return False
    finally:
        db.close()
