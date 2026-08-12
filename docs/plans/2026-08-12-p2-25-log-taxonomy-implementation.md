# P2-25 Log Taxonomy and History Search Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将系统日志文件选择器拆成当前日志、历史分类日志和历史执行日志，并让历史文件可按时间、名称或 execution ID 搜索。

**Architecture:** 保持 `/system-logs/files` 契约不变，在 GUI 增加一个纯函数目录分类器，将后端元数据转换为稳定的中文可搜索选项。`SystemLogViewer` 只消费分类结果并管理模式切换；现有 tail/history/filter/download/export 数据链不重写。

**Tech Stack:** React 18、TypeScript、Mantine 8、Node `node:test`、pytest 规则门、Vite。

---

### Task 1: 日志文件分类器

**Files:**
- Create: `gui/src/features/Reports/logFileCatalog.ts`
- Create: `gui/test/logFileCatalog.test.ts`

**Step 1: Write the failing test**

用 `node:test` 构造当前 `app.log`、归档 `app.log.2026-08-11`、执行
`exec-848a0000.log` 和未知归档四类元数据；断言分组、中文名称、日期回退、完整文件名和完整
execution ID 均进入 label/search text。

**Step 2: Run test to verify it fails**

Run: `node --experimental-strip-types --test gui/test/logFileCatalog.test.ts`

Expected: FAIL，因为 `logFileCatalog.ts` 尚不存在。

**Step 3: Write minimal implementation**

实现 `buildLogFileCatalog(files)`，返回 `current`、`historyCategory`、`historyExecution` 三组；
只按 `is_current` 和 `exec-*.log` 白名单分类，未知分类保留原文件名。

**Step 4: Run test to verify it passes**

Run: `node --experimental-strip-types --test gui/test/logFileCatalog.test.ts`

Expected: PASS。

**Step 5: Commit**

提交分类器与行为测试。

### Task 2: SystemLogViewer 模式接线

**Files:**
- Modify: `gui/src/features/Reports/components/SystemLogViewer.tsx`
- Modify: `api-service/tests/test_rule_gates.py`

**Step 1: Write the failing test**

新增 P2-25 组件接线门，断言界面有“当前日志/历史日志”和“分类日志/执行日志”，数据来自
`buildLogFileCatalog(files)`；历史模式切换会关闭刷新，自动刷新控件在历史模式禁用。

**Step 2: Run test to verify it fails**

Run: `PYTHONPATH=api-service /Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q api-service/tests/test_rule_gates.py -k p2_25`

Expected: FAIL，找不到分类器消费和模式控件。

**Step 3: Write minimal implementation**

增加 `logMode` 与 `historyKind` 状态；用两个 `SegmentedControl` 分流文件；`Select` 开启
`searchable` 并显示分类器产生的标签。进入历史模式时同步把刷新间隔置为 0，历史模式禁用
自动刷新菜单；无文件时显示分组空态。

**Step 4: Run test to verify it passes**

Run: 同 Step 2，并复跑 G14/G15。

Expected: PASS。

**Step 5: Commit**

提交组件接线与回归门。

### Task 3: Mock、Roadmap 与整体验证

**Files:**
- Modify: `gui/src/api/mockDatabase.ts`
- Modify: `docs/roadmap-first-call.md`

**Step 1: Write the failing test**

扩展 P2-25 门，要求 mock `/system-logs/files` 同时提供 current、历史分类和历史执行样本；要求
Roadmap 的 Current Focus 为 P2-25、WIP=1。

**Step 2: Run test to verify it fails**

Run: P2-25 定点门。

Expected: FAIL，mock 目前只有当前 `app.log`，Roadmap 仍显示 P3-19 暂停。

**Step 3: Write minimal implementation**

补三类 mock 文件元数据；将 Roadmap Current Focus 改为 P2-25，并登记 P1-49～P1-53、
P2-25～P2-34、P3-20～P3-21 的已批准队列。

**Step 4: Run full verification**

Run:

- `node --experimental-strip-types --test gui/test/logFileCatalog.test.ts`
- P2-25、G14、G15 定点 pytest
- 完整 `api-service/tests/test_rule_gates.py`
- `npm run build --prefix gui`
- `git diff --check`

Expected: 全部通过。

**Step 5: Commit**

提交 mock、Roadmap 和验证镜像。

