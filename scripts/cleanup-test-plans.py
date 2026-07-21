#!/usr/bin/env python3
"""清理测试计划管理列表的历史垃圾 (2026-07-21 用户拍板)。

背景: test_feature_gaps.py 等测试无 DB 隔离, 每次全量跑往开发库塞大量
测试计划残留 (Test Plan from Scenario / Auth/Stats/Priority/Queue Down/
Queue Test 各数十份) + 彩排产物, 计划管理列表爆到 100+ 条。跟队列僵尸
(cleanup-test-queue.py) 同源。

安全:
- 只删 name 不在保留白名单的计划; 白名单默认 = 现场调试主计划。
- running / paused 状态强制跳过 (绝不误删执行中的计划)。
- 逐条走 DELETE /test-plans/{id} 官方端点 (级联清队列/步骤/执行历史),
  不裸 SQL。
- 循环拉取直到无可删 (应对分页 + 跑测试期间的新增), 上限 50 轮防死循环。
"""
import argparse
import json
import sys
import urllib.error
import urllib.request

API = "http://localhost:8000/api/v1"


def api_get(path: str):
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as r:
        return json.load(r)


def api_delete(path: str) -> int:
    req = urllib.request.Request(f"{API}{path}", method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def delete_plan(plan_id: str) -> int:
    """删计划; queued 状态的计划 DELETE 返回 400 (在队列中不让删), 先出队再删。

    ⚠ running/paused 计划 DELETE 也返回 400, 但绝不能出队重删: 出队会把
    RUNNING 强制打回 READY, 于是执行中的计划被连带删掉 (agent 门 F3 竞态 —
    list 时 queued、删前被调度器提成 running)。所以 400 后重查 live 状态,
    只有确认 queued 才出队重删; running/paused/未知一律原样返回 400, 交上层
    当失败跳过 (绝不误删活计划)。"""
    code = api_delete(f"/test-plans/{plan_id}")
    if code != 400:
        return code
    try:
        plan = api_get(f"/test-plans/{plan_id}")
        if isinstance(plan, dict):
            plan = plan.get("data", plan)
        status = plan.get("status")
    except Exception:
        status = None
    if status != "queued":
        return code  # running/paused/未知 → 不碰队列, 失败上报
    api_delete(f"/test-plans/queue/{plan_id}")  # 出队 (不在队列则 404, 无害)
    return api_delete(f"/test-plans/{plan_id}")


def list_plans():
    d = api_get("/test-plans?limit=500")
    return d if isinstance(d, list) else d.get("items") or d.get("data") or []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--keep-name",
        action="append",
        default=None,
        help="name 完全等于此值的计划保留 (可多次; 默认保留'20260721 现场调试计划')",
    )
    args = ap.parse_args()
    keep = set(args.keep_name or ["20260721 现场调试计划"])
    print(f"保留白名单: {sorted(keep)}")

    deleted = failed = 0
    for round_i in range(1, 51):
        to_del = []
        for p in list_plans():
            name = p.get("name", "")
            if name in keep:
                continue
            if p.get("status") in ("running", "paused"):
                print(f"  · 保护跳过 (执行中/暂停): {name}")
                continue
            to_del.append(p)
        if not to_del:
            break
        for p in to_del:
            code = delete_plan(p["id"])
            if code < 400:
                deleted += 1
            else:
                failed += 1
                print(f"  ✗ {p['id']} ({p.get('name', '')[:30]}): {code}")
        print(f"[轮 {round_i}] 处理 {len(to_del)} 条")

    remain = list_plans()
    print(f"\n删除 {deleted} 条, 失败 {failed} 条; 剩余 {len(remain)} 条:")
    for p in remain:
        print(f"  [{p.get('status', ''):10}] {p.get('name')}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
