"""一次性清理: 自动化测试僵尸计划 (P3-15, 2026-08-01)。

来源: test_feature_gaps.py 曾无 DB 隔离, 每次全量测试往 dev 库塞测试计划/队列
条目 (#218 清过 801 条, 复发累计至 1201 条)。来源已断 (P3-15 给该文件补了
SQLite 隔离 fixture), 本脚本只清存量。

作用域 = **三重谓词** (Codex #263 R1 P1: 名字不唯一, 单按名删会误伤将来恰好
同名的真实计划): ① 8 个已知测试产物名精确匹配 ② created_by 限
test_feature_gaps 硬编码的三个测试身份 ③ created_at < 2026-08-01 (存量固化日,
之后新建的任何行不可达)。绝不按模糊模式全局删 (memory
feedback_bulk_mutation_scope_and_restrict_fk):
指向 test_plans 的外键共 **6 条边**, 全部 NO ACTION。本脚本删其中 4 条边的
子行 (顺序 三级 report_comparisons.report_id → 二级 test_reports /
test_plan_executions / test_queue / test_steps → 父行), 单事务;
**另两条边不删**: test_executions.test_plan_id (活表, 执行历史) 与
report_comparisons.baseline_plan_id (活功能) —— 有引用时父行 DELETE 会
IntegrityError 整体回滚 (保守方向), dry-run 会报这两条边的引用计数,
非零时先人工裁决再执行 (2026-08-01 实测均为 0)。

用法:
    python scripts/cleanup_zombie_test_plans.py            # dry-run, 只报数量
    python scripts/cleanup_zombie_test_plans.py --execute  # 真删 (单事务)

2026-08-01 dry-run 存量: plans=1201, queue=901, steps=1200, plan_execs=302,
reports=302, comparisons=0; 唯一非僵尸计划 = "20260721 现场调试计划" (保留)。
"""
import sys

from sqlalchemy import text

sys.path.insert(0, ".")
from app.db.database import SessionLocal  # noqa: E402

ZOMBIE_NAMES = (
    "Stats Test Plan", "Auth Test Plan", "Test Plan from Scenario",
    "Queue Down Test 1", "Queue Down Test 2", "Queue Test Plan 2",
    "Priority Test Plan", "Queue Test Plan 1",
)

ZOMBIE_CREATORS = ("test", "test_suite", "authenticated_user@example.com")
ZOMBIE_CUTOFF = "2026-08-01"  # 存量固化日 — 之后的行一律不可达

_PLAN_PRED = ("name IN :n AND created_by IN :c AND created_at < :cut")
_IN_PLANS = f"(SELECT id FROM test_plans WHERE {_PLAN_PRED})"
STEPS = [
    ("report_comparisons",
     f"DELETE FROM report_comparisons WHERE report_id IN "
     f"(SELECT id FROM test_reports WHERE test_plan_id IN {_IN_PLANS})"),
    ("test_reports", f"DELETE FROM test_reports WHERE test_plan_id IN {_IN_PLANS}"),
    ("test_plan_executions",
     f"DELETE FROM test_plan_executions WHERE test_plan_id IN {_IN_PLANS}"),
    ("test_queue", f"DELETE FROM test_queue WHERE test_plan_id IN {_IN_PLANS}"),
    ("test_steps", f"DELETE FROM test_steps WHERE test_plan_id IN {_IN_PLANS}"),
    ("test_plans", f"DELETE FROM test_plans WHERE {_PLAN_PRED}"),
]


_BIND = {"n": ZOMBIE_NAMES, "c": ZOMBIE_CREATORS, "cut": ZOMBIE_CUTOFF}


def main() -> None:
    execute = "--execute" in sys.argv
    db = SessionLocal()
    try:
        print("僵尸存量 (精确名匹配, 逐表):")
        counts = [
            ("test_plans", f"SELECT COUNT(*) FROM test_plans WHERE {_PLAN_PRED}"),
            ("test_queue", f"SELECT COUNT(*) FROM test_queue WHERE test_plan_id IN {_IN_PLANS}"),
            ("test_steps", f"SELECT COUNT(*) FROM test_steps WHERE test_plan_id IN {_IN_PLANS}"),
            ("test_plan_executions",
             f"SELECT COUNT(*) FROM test_plan_executions WHERE test_plan_id IN {_IN_PLANS}"),
            ("test_reports", f"SELECT COUNT(*) FROM test_reports WHERE test_plan_id IN {_IN_PLANS}"),
            ("report_comparisons (report_id 边)",
             f"SELECT COUNT(*) FROM report_comparisons WHERE report_id IN "
             f"(SELECT id FROM test_reports WHERE test_plan_id IN {_IN_PLANS})"),
        ]
        for tab, sql in counts:
            print(f"  {tab}: {db.execute(text(sql), _BIND).scalar()}")
        blockers = [
            ("test_executions.test_plan_id (不删, 活表)",
             f"SELECT COUNT(*) FROM test_executions WHERE test_plan_id IN {_IN_PLANS}"),
            ("report_comparisons.baseline_plan_id (不删, 活功能)",
             f"SELECT COUNT(*) FROM report_comparisons WHERE baseline_plan_id IN {_IN_PLANS}"),
        ]
        blocked = False
        for tab, sql in blockers:
            nb = db.execute(text(sql), _BIND).scalar()
            print(f"  ⚠ {tab}: {nb}")
            blocked = blocked or nb > 0
        if blocked and execute:
            print("被引用边非零 — 先人工裁决, 本次不执行 (父行 DELETE 会 IntegrityError)。")
            return
        keep = db.execute(
            text(f"SELECT COUNT(*), MIN(name) FROM test_plans WHERE NOT ({_PLAN_PRED})"),
            _BIND,
        ).fetchone()
        print(f"  保留 (谓词外): {keep[0]} 条, 例: {keep[1]}")
        # 逐 created_by 分布 — 人工核对"全是测试身份"再 --execute
        dist = db.execute(text(
            f"SELECT created_by, COUNT(*) FROM test_plans WHERE {_PLAN_PRED} "
            "GROUP BY created_by"), _BIND).fetchall()
        for cb, cnt in dist:
            print(f"  命中分布 created_by={cb!r}: {cnt}")
        if not execute:
            print("\ndry-run — 加 --execute 才真删 (单事务, 三级→二级→父行)。")
            return
        for name, sql in STEPS:
            n = db.execute(text(sql), _BIND).rowcount
            print(f"  已删 {name}: {n}")
        db.commit()
        print("完成 (已提交)。")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
