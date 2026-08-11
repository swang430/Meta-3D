"""清理 P1-38 已确认的两种历史 ``test_suite`` 告警污染。

默认只做 dry-run；只有显式传入 ``--execute`` 才在单事务中删除。删除谓词是
source、created_by、cutoff 与五个内容字段的精确白名单，任何近似数据都保留。

用法：
    python scripts/cleanup_test_suite_alerts.py
    python scripts/cleanup_test_suite_alerts.py --execute
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import NamedTuple

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.orm import Session


_API_SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(_API_SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(_API_SERVICE_ROOT))

from app.db.database import SessionLocal  # noqa: E402
from app.models.alert import Alert  # noqa: E402


HISTORICAL_CUTOFF = datetime(2026, 8, 2, tzinfo=timezone.utc)


class CleanupResult(NamedTuple):
    execute: bool
    matched: int
    deleted: int
    candidate_ids: tuple


def _historical_test_suite_predicate():
    identity = and_(
        Alert.source == "test_suite",
        Alert.created_by == "test_suite",
        Alert.created_at < HISTORICAL_CUTOFF,
    )
    warning_fixture = and_(
        Alert.title == "WARNING: Alert",
        Alert.message == "Test alert",
        Alert.severity == "warning",
        Alert.alert_type == "warning",
        Alert.status == "active",
    )
    dismissed_info_fixture = and_(
        Alert.title == "INFO: Alert",
        Alert.message == "Alert to dismiss",
        Alert.severity == "info",
        Alert.alert_type == "info",
        Alert.status == "dismissed",
    )
    return and_(identity, or_(warning_fixture, dismissed_info_fixture))


def cleanup_test_suite_alerts(
    db: Session,
    *,
    execute: bool = False,
) -> CleanupResult:
    """报告或删除精确命中的历史测试告警；异常时回滚并原样抛出。"""
    try:
        candidate_ids = tuple(
            db.scalars(
                select(Alert.id)
                .where(_historical_test_suite_predicate())
                .order_by(Alert.created_at, Alert.id)
            ).all()
        )
        if not execute:
            return CleanupResult(False, len(candidate_ids), 0, candidate_ids)

        deleted = 0
        if candidate_ids:
            # 再带完整谓词，避免候选预览与 DELETE 之间内容被改写后仍按旧 id 删除。
            result = db.execute(
                delete(Alert).where(
                    Alert.id.in_(candidate_ids),
                    _historical_test_suite_predicate(),
                )
            )
            deleted = result.rowcount or 0
        db.commit()
        return CleanupResult(True, len(candidate_ids), deleted, candidate_ids)
    except Exception:
        db.rollback()
        raise


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="精确清理 2026-08-02 前的两种 test_suite 告警污染",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="提交删除；不传时仅报告命中数量",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    db = SessionLocal()
    try:
        result = cleanup_test_suite_alerts(db, execute=args.execute)
        mode = "execute" if result.execute else "dry-run"
        print(f"{mode}: matched={result.matched}, deleted={result.deleted}")
        for candidate_id in result.candidate_ids:
            print(f"  {candidate_id}")
        if not result.execute:
            print("未修改数据库；确认候选后加 --execute 才会提交删除。")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
