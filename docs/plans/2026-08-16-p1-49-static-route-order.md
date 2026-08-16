# P1-49 Static Route Ordering Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让 `/calibration/channel/temporal/latest` 与 `/topologies/default` 命中各自静态 handler，而不是被同级 UUID 参数路由抢先匹配并返回 422。

**Architecture:** 保持现有 FastAPI router、URL、handler 与服务层不变，只把两个静态 GET 声明移动到同级参数 GET 声明之前。用真实 TestClient + 隔离 SQLite 锁住 HTTP 行为，并删除 G19 的两个临时例外，使全仓重新要求零静态路由遮挡。

**Tech Stack:** FastAPI、Starlette 路由匹配、SQLAlchemy、pytest、FastAPI TestClient。

---

### Task 1: 建立真实 HTTP RED 保护

**Files:**
- Create: `api-service/tests/test_p1_49_static_route_order.py`

**Step 1: 写隔离数据库 fixture**

使用 `sqlite://`、`StaticPool`、`Base.metadata.create_all/drop_all`，并仅在本测试内覆盖 `get_db`。

**Step 2: 写两个静态端点行为测试**

```python
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/calibration/channel/temporal/latest",
        "/api/v1/topologies/default",
    ],
)
def test_static_route_reaches_handler_instead_of_uuid_validation(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert "uuid_parsing" not in response.text
```

空库下两个目标 handler 的权威结果都是 404；旧顺序应返回 422 `uuid_parsing`。

**Step 3: 写合法 UUID 详情路由保护**

```python
@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/calibration/channel/temporal/{uuid4()}",
        f"/api/v1/topologies/{uuid4()}",
    ],
)
def test_uuid_detail_routes_remain_reachable(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert "uuid_parsing" not in response.text
```

**Step 4: 运行测试并确认 RED**

Run:

```bash
cd api-service
PYTHONPATH=. /Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q tests/test_p1_49_static_route_order.py
```

Expected: 两个静态端点用例失败，实际状态 422；两个合法 UUID 用例通过。

**Step 5: 提交 RED**

```bash
git add api-service/tests/test_p1_49_static_route_order.py
git commit -m "test: reproduce P1-49 static route shadows"
```

### Task 2: 最小移动两个静态路由

**Files:**
- Modify: `api-service/app/api/channel_calibration.py`
- Modify: `api-service/app/api/topology.py`

**Step 1: 移动 temporal latest handler**

把完整的 `@router.get("/temporal/latest")` handler 移到
`@router.get("/temporal/{calibration_id}")` 之前；handler 内容不变。

**Step 2: 移动 topology default handler**

把完整的 `@router.get("/default")` handler 移到
`@router.get("/{topology_id}")` 之前；handler 内容不变。

**Step 3: 运行 HTTP 测试并确认 GREEN**

Run:

```bash
cd api-service
PYTHONPATH=. /Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q tests/test_p1_49_static_route_order.py
```

Expected: 全部通过。

**Step 4: 提交最小生产修复**

```bash
git add api-service/app/api/channel_calibration.py api-service/app/api/topology.py
git commit -m "fix: prioritize P1-49 static routes"
```

### Task 3: 收紧 G19 为零例外

**Files:**
- Modify: `api-service/tests/test_rule_gates.py`

**Step 1: 删除两个 known_existing 元组**

把 `known_existing` 改为空集合，并更新注释为“P1-49 已清零存量，后续不得新增”。

**Step 2: 运行 G19**

Run:

```bash
cd api-service
PYTHONPATH=. /Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q tests/test_rule_gates.py -k g19
```

Expected: 2 passed。

**Step 3: 提交守门收口**

```bash
git add api-service/tests/test_rule_gates.py
git commit -m "test: remove resolved P1-49 route exceptions"
```

### Task 4: 更新 roadmap 到外审前状态并完整验证

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Step 1: 同步事实镜像**

把 P1-49 标为实现完成、等待外审；Current Focus 保持 P1-49、WIP=1；关闭原 Discovered
中的两个静态路由例外描述，并保留历史来源说明。

**Step 2: 运行相关回归**

Run:

```bash
cd api-service
PYTHONPATH=. /Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_p1_49_static_route_order.py tests/test_rule_gates.py
```

Expected: 全部通过。

**Step 3: 运行语法与 diff 检查**

Run:

```bash
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m compileall -q api-service/app
git diff --check origin/main...HEAD
```

Expected: 零错误、零 whitespace 问题。

**Step 4: 提交 roadmap**

```bash
git add docs/roadmap-first-call.md
git commit -m "docs: advance P1-49 route fix"
```

### Task 5: 内审、Ready PR 与两轮外审收口

**Files:**
- Potentially modify only files already in this plan when a verified P1 requires it.

**Step 1: 按 AGENTS.md 做完整内审**

枚举两个静态路由的所有生产/消费方；验证合法 UUID、404 语义、G19 全集与 roadmap 镜像。

**Step 2: 推送并创建 Ready PR**

```bash
git push -u origin codex/p1-49-static-route-order
gh pr create --base main --head codex/p1-49-static-route-order --title "fix: restore P1-49 static routes" --body-file <prepared-body>
```

**Step 3: 执行 R1**

触发 `@codex review`；核实并处理本片内可执行意见。P1 必修；本片内 P2 可一并收口。

**Step 4: 在 R2 前完成 roadmap 最终状态**

把 P1-49 标记完成，Current Focus 指向 P1-50、WIP=0，并提交推送。

**Step 5: 执行最后一轮 R2**

再次触发 `@codex review`。R2 无 P1立即 merge；R2 若仍有 P1，修复并通过内审/回归后 merge，
不触发 R3。R2 的 P2/P3 只报告一次，不自动写入 Discovered。

**Step 6: 合并后核验 main**

确认 merge commit 是 `origin/main` 祖先，roadmap 的 P1-49/P1-50/WIP 三处一致；随后自动创建
P1-50 独立分支并开始设计与开发，继续维持逐片 WIP=1。只有出现真实阻塞时才请求用户介入。
