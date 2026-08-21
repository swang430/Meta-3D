"""把正式执行的系统失败一次性发布到活动告警摘要。

调用方必须先提交 ``TestExecution.status='failed'``；本模块再用独立 session
best-effort 写告警。这样告警表故障不会把真实执行终态回滚成 running。

P2-34 发布结果契约：
- 返回值是 outcome 字符串（``OUTCOME_*`` 常量），不再是混叠的 bool ——
  「按设计跳过」「去重命中」「告警写入失败」对读方是三种不同的结果。
- 尝试过发布的三种结果（published / duplicate / failed）best-effort 记进
  ``TestExecution.config["failure_alert"]``：告警事务之后的**第二个独立事务**，
  记录写入失败同样绝不改写执行终态，只留日志。跳过类判定可从行自身重推导，
  不落库（也避免污染 VRT 行的 config）。
- 历史行没有 ``failure_alert`` 键 = **未记录**（P2-34 之前的行 / 记录写入
  失败），读方绝不能把它当"发布成功"。白名单解析见
  :func:`resolve_recorded_outcome`。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.orm.attributes import flag_modified

from app.db.database import SessionLocal
from app.models.alert import Alert, AlertSeverity, AlertStatus
from app.models.test_plan import TestExecution

logger = logging.getLogger(__name__)

EXECUTION_FAILED_ALERT_TYPE = "execution_failed"
FORMAL_EXECUTION_SOURCES = frozenset({"test_case_runner", "commissioning_api"})

# ── 发布结果的形态空间（设计稿 §3.1，白名单）──
OUTCOME_PUBLISHED = "published"            # 新告警行已 commit
OUTCOME_DUPLICATE = "duplicate"            # 生命周期去重命中（该执行已有告警）
OUTCOME_FAILED = "failed"                  # 告警写入异常（告警表故障等）
OUTCOME_SKIPPED_MISSING = "skipped_missing"        # 执行行不存在
OUTCOME_SKIPPED_NOT_FAILED = "skipped_not_failed"  # 状态非 failed（防御分支）
OUTCOME_SKIPPED_NOT_FORMAL = "skipped_not_formal"  # 非正式源（VRT / 调试等）

#: 会落进 ``config["failure_alert"]`` 的 outcome 全集 —— 读方白名单的唯一真值源。
RECORDED_OUTCOMES = frozenset({OUTCOME_PUBLISHED, OUTCOME_DUPLICATE, OUTCOME_FAILED})

CONFIG_RECORD_KEY = "failure_alert"

_ERROR_SUMMARY_LIMIT = 500  # 摘要进 JSONB；完整 traceback 只进日志


def resolve_recorded_outcome(config: Any) -> Optional[str]:
    """读一行执行的告警发布记录；白名单解析。

    返回 ``None`` = **未记录** —— P2-34 之前的历史行、记录写入失败、或该行
    不适用（非失败 / 非正式执行）。未记录不是"发布成功"；读方（历史列表、
    GUI）必须把 None 展示成"未记录"，不得给出任何肯定结论。
    畸形形状（记录非 dict / outcome 不在白名单）同样收窄成 None ——
    照 ``_to_history_item`` 的畸形收窄先例，不许毒整页列表。
    """
    if not isinstance(config, dict):
        return None
    record = config.get(CONFIG_RECORD_KEY)
    if not isinstance(record, dict):
        return None
    outcome = record.get("outcome")
    if outcome in RECORDED_OUTCOMES:
        return outcome
    return None


def _record_publish_outcome(
    db,
    execution_id: UUID,
    outcome: str,
    alert_id: Optional[str],
    error_summary: Optional[str],
) -> None:
    """把发布结果 best-effort 记进 ``execution.config``（第二个独立事务）。

    绝不触碰 ``TestExecution.status``；任何异常只 rollback + log，不向调用方
    泄漏 —— 记录写入失败跟告警写入失败一样，不得反噬执行终态。
    duplicate 仅补缺（行上已有形状合法的记录时保留原记录 —— 守「已处置的
    告警不得重新 active」禁令的记录侧对偶）；published / failed 总是写
    （重试成功 / 再次失败是真实的状态推进）。
    """
    try:
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == execution_id)
            .first()
        )
        if execution is None:
            return
        cfg = dict(execution.config) if isinstance(execution.config, dict) else {}
        if outcome == OUTCOME_DUPLICATE and isinstance(
            cfg.get(CONFIG_RECORD_KEY), dict
        ):
            return
        record: dict[str, Any] = {
            "outcome": outcome,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }
        if alert_id:
            record["alert_id"] = alert_id
        if error_summary:
            record["error"] = error_summary
        cfg[CONFIG_RECORD_KEY] = record
        execution.config = cfg
        flag_modified(execution, "config")
        db.commit()
    except Exception:  # noqa: BLE001 - 记录失败不得反噬执行终态与告警结果
        db.rollback()
        logger.exception(
            "执行 %s 的告警发布结果记录写入失败（执行终态与告警结果不受影响）",
            execution_id,
        )


def emit_execution_failed_alert(execution_id: UUID) -> str:
    """为一个新进入 failed 的正式执行创建告警，并记录发布结果。

    返回发布结果 outcome（``OUTCOME_*``）。去重覆盖告警全部生命周期：
    操作员已 acknowledge/resolve/dismiss 的同一执行不得因调用方重试而
    重新变成 active。
    """
    db = SessionLocal()
    try:
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == execution_id)
            .first()
        )
        if execution is None:
            return OUTCOME_SKIPPED_MISSING
        if execution.status != "failed":
            return OUTCOME_SKIPPED_NOT_FAILED
        if execution.executed_by not in FORMAL_EXECUTION_SOURCES:
            return OUTCOME_SKIPPED_NOT_FORMAL

        existing = (
            db.query(Alert.id)
            .filter(
                Alert.alert_type == EXECUTION_FAILED_ALERT_TYPE,
                Alert.related_entity_type == "test_execution",
                Alert.related_entity_id == execution.id,
            )
            .first()
        )
        alert_id: Optional[str] = None
        error_summary: Optional[str] = None
        if existing is not None:
            outcome = OUTCOME_DUPLICATE
            alert_id = str(existing[0])
        else:
            config = execution.config or {}
            reason = execution.error_message or config.get("error_message")
            message = f"执行 {execution.id} 已失败"
            if reason:
                message += f"：{reason}"
            alert = Alert(
                title="正式测试执行失败",
                message=message,
                severity=AlertSeverity.ERROR.value,
                alert_type=EXECUTION_FAILED_ALERT_TYPE,
                source=execution.executed_by,
                status=AlertStatus.ACTIVE.value,
                related_entity_type="test_execution",
                related_entity_id=execution.id,
                created_by=execution.executed_by,
            )
            try:
                db.add(alert)
                db.commit()
            except Exception as exc:  # noqa: BLE001 - 告警失败不得改写真实执行终态
                db.rollback()
                logger.exception(
                    "执行 %s 的失败告警写入失败（执行终态保持 failed）", execution_id
                )
                outcome = OUTCOME_FAILED
                error_summary = f"{type(exc).__name__}: {exc}"[:_ERROR_SUMMARY_LIMIT]
            else:
                outcome = OUTCOME_PUBLISHED
                alert_id = str(alert.id)
                logger.info("已发布执行失败告警: execution=%s", execution.id)

        _record_publish_outcome(db, execution_id, outcome, alert_id, error_summary)
        return outcome
    except Exception:  # noqa: BLE001 - 告警链任何故障都不得反噬执行终态
        db.rollback()
        logger.exception(
            "执行 %s 的失败告警发布异常（执行终态保持 failed）", execution_id
        )
        return OUTCOME_FAILED
    finally:
        db.close()
