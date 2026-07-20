#!/usr/bin/env python3
"""清理执行队列历史僵尸条目 (2026-07-20 用户拍板)。

背景: dev DB 的 test_queue 积累 801 条开发测试残留 (Priority Test Plan /
Queue Down Test / Stats Test Plan 等), 07-03 机动任务记录在案待拍板;
2026-07-20 用户实操撞上"找不到最新排队条目"并拍板全清。

安全性: 只删 test_queue 行 (排队关系), 不动 TestPlan / TestCase / 执行
历史; 逐条走 DELETE /test-plans/queue/{plan_id} 官方端点 (含级联/校验),
不裸 SQL。支持 --keep-name 保留匹配名称的条目 (默认无保留, 全清)。
"""
import argparse
import sys

import httpx

API = "http://localhost:8000/api/v1"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--keep-name", default=None,
                    help="计划名含此子串的队列条目保留不删")
    args = ap.parse_args()

    http = httpx.Client(timeout=30.0)
    r = http.get(f"{API}/test-plans/queue", params={"limit": 1000})
    r.raise_for_status()
    items = r.json().get("items", [])
    print(f"队列现有 {len(items)} 条")

    ok = fail = kept = 0
    for it in items:
        plan_id = it["queue_item"]["test_plan_id"]
        plan = it.get("test_plan") or {}
        name = plan.get("name", "")
        # 门审 #218 F1: 执行中/暂停的计划绝不出队 — DELETE 端点会无条件把
        # 计划打回 ready, runner 还在打仪器时状态就错乱 (且单飞门 DB 判据被清)
        if plan.get("status") in ("running", "paused"):
            kept += 1
            print(f"  · 保留 (执行中/暂停): {name[:40]}")
            continue
        if args.keep_name and args.keep_name in name:
            kept += 1
            continue
        resp = http.delete(f"{API}/test-plans/queue/{plan_id}")
        if resp.status_code < 400:
            ok += 1
        else:
            fail += 1
            print(f"  ✗ {plan_id} ({name[:30]}): {resp.status_code}")

    r2 = http.get(f"{API}/test-plans/queue", params={"limit": 1000})
    remain = len(r2.json().get("items", []))
    print(f"删除 {ok} 条, 失败 {fail} 条, 保留 {kept} 条; 清理后剩余 {remain} 条")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
