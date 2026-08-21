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
from uuid import UUID, uuid4

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


def _rollback_best_effort(db: Any, execution_id: UUID, context: str) -> bool:
    """尝试回滚并返回 session 是否可安全复用。"""
    if db is None:
        return False
    try:
        db.rollback()
        return True
    except Exception:  # noqa: BLE001 - rollback 失败不能改写已确定的发布结果
        logger.exception("执行 %s 的%s回滚失败（发布结果不受影响）", execution_id, context)
        return False


def _close_best_effort(db: Any, execution_id: UUID) -> None:
    """关闭故障只留日志，不能覆盖函数已经确定的 outcome。"""
    if db is None:
        return
    try:
        db.close()
    except Exception:  # noqa: BLE001 - close 失败不能泄漏到正式执行链
        logger.exception("执行 %s 的告警会话关闭失败（发布结果不受影响）", execution_id)


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
    # 内审 F1：先验 str 再查白名单 —— list / dict 这类不可哈希的脏值会让
    # `in set` 抛 TypeError，穿到 _to_history_item 就把整页历史吞成空表。
    if isinstance(outcome, str) and outcome in RECORDED_OUTCOMES:
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
    duplicate 保留已有 published/duplicate；旧 failed 或畸形记录会推进为
    duplicate 并关联真实 Alert（现存告警已证伪“发布失败”）。published / failed
    总是写（重试成功 / 再次失败是真实的状态推进）。非对象 config 视为历史证据，
    原样保留并跳过记录，绝不为新增键抹掉整份 JSON。
    """
    try:
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == execution_id)
            .first()
        )
        if execution is None:
            return
        if execution.config is not None and not isinstance(execution.config, dict):
            logger.warning(
                "执行 %s 的 config 不是对象，保留原始证据并跳过告警结果记录",
                execution_id,
            )
            return
        cfg = dict(execution.config or {})
        recorded_outcome = resolve_recorded_outcome(cfg)
        if outcome == OUTCOME_DUPLICATE and recorded_outcome in {
            OUTCOME_PUBLISHED,
            OUTCOME_DUPLICATE,
        }:
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
        _rollback_best_effort(db, execution_id, "告警结果记录事务")
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
    db: Any = None
    try:
        db = SessionLocal()
        record_session_usable = True
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
            config = execution.config if isinstance(execution.config, dict) else {}
            reason = execution.error_message or config.get("error_message")
            message = f"执行 {execution.id} 已失败"
            if reason:
                message += f"：{reason}"
            new_alert_id = uuid4()
            alert = Alert(
                id=new_alert_id,
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
                record_session_usable = _rollback_best_effort(
                    db, execution_id, "告警写入事务"
                )
                logger.exception(
                    "执行 %s 的失败告警写入失败（执行终态保持 failed）", execution_id
                )
                outcome = OUTCOME_FAILED
                error_summary = f"{type(exc).__name__}: {exc}"[:_ERROR_SUMMARY_LIMIT]
            else:
                outcome = OUTCOME_PUBLISHED
                alert_id = str(new_alert_id)
                logger.info("已发布执行失败告警: execution=%s", execution_id)

        if record_session_usable:
            _record_publish_outcome(
                db, execution_id, outcome, alert_id, error_summary
            )
        return outcome
    except Exception as exc:  # noqa: BLE001 - 告警链任何故障都不得反噬执行终态
        record_session_usable = _rollback_best_effort(
            db, execution_id, "告警发布外层事务"
        )
        error_summary = f"{type(exc).__name__}: {exc}"[:_ERROR_SUMMARY_LIMIT]
        if db is not None and record_session_usable:
            _record_publish_outcome(
                db,
                execution_id,
                OUTCOME_FAILED,
                alert_id=None,
                error_summary=error_summary,
            )
        logger.exception(
            "执行 %s 的失败告警发布异常（执行终态保持 failed）", execution_id
        )
        return OUTCOME_FAILED
    finally:
        _close_best_effort(db, execution_id)
