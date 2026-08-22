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

import json
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
LOCAL_HANDOFF_ALERT_KEY = "local_control_handoff_failed"

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
            # Alert 已在上一事务提交；本事务仍需独立锁住 execution 后再合并
            # 整列 JSON config，避免覆盖并发落盘的 Local 交接或其他最终证据。
            .with_for_update()
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


def _reconcile_ambiguous_alert_commit(
    execution_id: UUID,
    alert_id: UUID,
    commit_error_summary: str,
) -> str:
    """用新会话查证结果未知的 Alert COMMIT，并在同一新会话记录真值。

    ``commit()`` 抛错不能证明事务未提交：数据库可能已经落行，只是确认包在
    返回客户端前丢失。旧 session 的事务状态也不再可信，因此只按预先冻结的
    ``alert_id`` 在新连接上查权威行。存在可确定为 published；一次查不到仍可能
    早于原事务最终提交，跟新连接不可用一样只能保持历史**未记录**，不得猜成
    failed。
    """
    verify_db: Any = None
    try:
        verify_db = SessionLocal()
        committed = (
            verify_db.query(Alert.id)
            .filter(
                Alert.id == alert_id,
                Alert.alert_type == EXECUTION_FAILED_ALERT_TYPE,
                Alert.related_entity_type == "test_execution",
                Alert.related_entity_id == execution_id,
            )
            .first()
        )
        if committed is None:
            logger.warning(
                "执行 %s 的告警 COMMIT 结果暂不可见，历史保持未记录：%s",
                execution_id,
                commit_error_summary,
            )
            return OUTCOME_FAILED
        outcome = OUTCOME_PUBLISHED
        resolved_alert_id: Optional[str] = str(alert_id)
        error_summary: Optional[str] = None
        logger.info(
            "执行 %s 的告警 COMMIT 确认丢失，但已按冻结 ID 查证发布成功",
            execution_id,
        )
        _record_publish_outcome(
            verify_db,
            execution_id,
            outcome,
            resolved_alert_id,
            error_summary,
        )
        return outcome
    except Exception:  # noqa: BLE001 - 查证失败必须保持未记录，不能猜事务结果
        _rollback_best_effort(verify_db, execution_id, "告警 COMMIT 查证事务")
        logger.exception(
            "执行 %s 的告警 COMMIT 结果无法查证，发布历史保持未记录",
            execution_id,
        )
        return OUTCOME_FAILED
    finally:
        _close_best_effort(verify_db, execution_id)


def _reconcile_ambiguous_alert_update(
    execution_id: UUID,
    alert_id: UUID,
    intended_message: str,
    intended_status: str,
    intended_extra_data: Optional[str],
    commit_error_summary: str,
) -> str:
    """用新会话核对既有告警正文与生命周期更新的 COMMIT 真值。"""
    verify_db: Any = None
    try:
        verify_db = SessionLocal()
        committed = (
            verify_db.query(Alert.id)
            .filter(
                Alert.id == alert_id,
                Alert.alert_type == EXECUTION_FAILED_ALERT_TYPE,
                Alert.related_entity_type == "test_execution",
                Alert.related_entity_id == execution_id,
                Alert.message == intended_message,
                Alert.status == intended_status,
                Alert.extra_data == intended_extra_data,
            )
            .first()
        )
        if committed is None:
            logger.warning(
                "执行 %s 的既有告警正文更新结果暂不可见，历史保持原记录：%s",
                execution_id,
                commit_error_summary,
            )
            return OUTCOME_FAILED
        _record_publish_outcome(
            verify_db,
            execution_id,
            OUTCOME_DUPLICATE,
            str(alert_id),
            None,
        )
        logger.info(
            "执行 %s 的既有告警更新确认丢失，但已按冻结 ID 与正文查证成功",
            execution_id,
        )
        return OUTCOME_DUPLICATE
    except Exception:  # noqa: BLE001 - 查证失败不得猜测正文是否已提交
        _rollback_best_effort(verify_db, execution_id, "既有告警更新查证事务")
        logger.exception(
            "执行 %s 的既有告警正文更新结果无法查证，历史保持原记录",
            execution_id,
        )
        return OUTCOME_FAILED
    finally:
        _close_best_effort(verify_db, execution_id)


def emit_execution_failed_alert(execution_id: UUID) -> str:
    """为一个新进入 failed 的正式执行创建告警，并记录发布结果。

    返回发布结果 outcome（``OUTCOME_*``）。去重覆盖告警全部生命周期：
    操作员已 acknowledge/resolve/dismiss 的同一执行不得因普通重试而重新
    变成 active；但后来新增的 Local 交接失败代表仪表可能仍处于 Remote，
    必须恰好重新激活一次。
    """
    db: Any = None
    try:
        db = SessionLocal()
        record_session_usable = True
        outcome_already_recorded = False
        execution = (
            db.query(TestExecution)
            .filter(TestExecution.id == execution_id)
            # execution 行必然存在，先锁它来串行化同一执行的“查无告警→首建”
            # 与后续去重。PostgreSQL 对不存在的 Alert 行没有 gap lock，仅锁
            # Alert 不能阻止两个 emitter 各插一条不同 UUID 的重复告警。
            .with_for_update()
            .first()
        )
        if execution is None:
            return OUTCOME_SKIPPED_MISSING
        if execution.status != "failed":
            return OUTCOME_SKIPPED_NOT_FAILED
        if execution.executed_by not in FORMAL_EXECUTION_SOURCES:
            return OUTCOME_SKIPPED_NOT_FORMAL

        config = execution.config if isinstance(execution.config, dict) else {}
        reason = execution.error_message or config.get("error_message")
        message = f"执行 {execution.id} 已失败"
        if reason:
            message += f"：{reason}"

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
            existing_alert = (
                db.query(Alert)
                .filter(Alert.id == existing[0])
                # Local 交接失败是会重开同一告警的一次性安全事实。必须先锁住
                # 权威 Alert 行再读 marker 与 lifecycle；否则两个 emitter 都可能
                # 从旧快照判断为“首次”，后提交者会覆盖操作员刚完成的确认。
                .with_for_update()
                .first()
            )
            if existing_alert is None:
                raise RuntimeError(
                    f"执行 {execution.id} 的既有失败告警在加锁读取时消失"
                )
            try:
                alert_metadata = json.loads(existing_alert.extra_data or "{}")
            except (TypeError, ValueError):
                alert_metadata = {}
            if not isinstance(alert_metadata, dict):
                alert_metadata = {}
            handoff_fact_new = (
                config.get(LOCAL_HANDOFF_ALERT_KEY) is True
                and alert_metadata.get(LOCAL_HANDOFF_ALERT_KEY) is not True
            )
            message_changed = existing_alert.message != message
            # 普通原因更新只刷新正文并保留操作员 lifecycle。Local 交接失败是
            # 新的安全事实：首次进入同一告警时重新激活并置为未读；结构化 marker
            # 与状态同行提交，保证后续普通重试不会再次重开。
            if message_changed or handoff_fact_new:
                existing_alert.message = message
                if handoff_fact_new:
                    existing_alert.status = AlertStatus.ACTIVE.value
                    existing_alert.is_read = False
                    existing_alert.acknowledged_at = None
                    existing_alert.resolved_at = None
                    existing_alert.acknowledged_by = None
                    alert_metadata[LOCAL_HANDOFF_ALERT_KEY] = True
                    existing_alert.extra_data = json.dumps(
                        alert_metadata,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                frozen_alert_id = existing_alert.id
                intended_status = existing_alert.status
                intended_extra_data = existing_alert.extra_data
                try:
                    db.commit()
                except Exception as exc:  # noqa: BLE001 - COMMIT 结果需独立查证
                    _rollback_best_effort(db, execution_id, "既有告警更新事务")
                    error_summary = (
                        f"{type(exc).__name__}: {exc}"
                    )[:_ERROR_SUMMARY_LIMIT]
                    outcome = _reconcile_ambiguous_alert_update(
                        execution_id,
                        frozen_alert_id,
                        message,
                        intended_status,
                        intended_extra_data,
                        error_summary,
                    )
                    outcome_already_recorded = True
                else:
                    outcome = OUTCOME_DUPLICATE
            else:
                outcome = OUTCOME_DUPLICATE
            alert_id = str(existing_alert.id)
        else:
            new_alert_id = uuid4()
            handoff_fact_present = (
                config.get(LOCAL_HANDOFF_ALERT_KEY) is True
            )
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
                extra_data=(
                    json.dumps(
                        {LOCAL_HANDOFF_ALERT_KEY: True},
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                    if handoff_fact_present
                    else None
                ),
            )
            try:
                db.add(alert)
                db.commit()
            except Exception as exc:  # noqa: BLE001 - 告警失败不得改写真实执行终态
                _rollback_best_effort(db, execution_id, "告警写入事务")
                logger.exception(
                    "执行 %s 的失败告警 COMMIT 未获确认（执行终态保持 failed）",
                    execution_id,
                )
                error_summary = f"{type(exc).__name__}: {exc}"[:_ERROR_SUMMARY_LIMIT]
                outcome = _reconcile_ambiguous_alert_commit(
                    execution_id,
                    new_alert_id,
                    error_summary,
                )
                outcome_already_recorded = True
            else:
                outcome = OUTCOME_PUBLISHED
                alert_id = str(new_alert_id)
                logger.info("已发布执行失败告警: execution=%s", execution_id)

        if record_session_usable and not outcome_already_recorded:
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
