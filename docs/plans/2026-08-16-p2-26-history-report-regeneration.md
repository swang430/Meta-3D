# P2-26 Historical MIMO Report Regeneration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让操作员从报告列表识别并安全重生成被 provenance 门封锁的历史 MIMO 报告，同时保留 UNKNOWN/N/A fail-closed 语义。

**Architecture:** 后端列表复用现有 MIMO 与 trust schema 判据计算恢复状态；GUI 只消费该权威状态并调用现有 generate endpoint。下载错误增加 Blob JSON detail 解析作为旧缓存兜底，不新增第二套生成器。

**Tech Stack:** FastAPI、SQLAlchemy、Pydantic、React、TypeScript、TanStack Query、Mantine、pytest、Node test runner。

---

### Task 1: 锁定恢复状态后端契约

**Files:**
- Modify: `api-service/app/schemas/report.py`
- Modify: `api-service/app/api/report.py`
- Test: `api-service/tests/test_mimo_ota_report_verified_backcompat.py`

1. 先写列表 RED：legacy single execution 可恢复；sanitized/非 MIMO 无需恢复；缺执行/多执行不可恢复。
2. 运行 `pytest -q tests/test_mimo_ota_report_verified_backcompat.py -k report_list_regeneration`，确认因 summary 无恢复字段而失败。
3. 最小实现三个 summary 字段，并复用现有 MIMO/trust/关联执行判据。
4. 复跑转绿，提交 `feat: expose historical report recovery state`。

### Task 2: 锁定 GUI 恢复动作与错误文本

**Files:**
- Modify: `gui/src/features/Reports/types/index.ts`
- Modify: `gui/src/features/Reports/api/reportsAPI.ts`
- Modify: `gui/src/features/Reports/components/ReportList.tsx`
- Test: `gui/test/reportRecovery.test.ts`

1. 先写 GUI RED：completed legacy 可恢复行显示恢复并隐藏下载；不可恢复行禁用且显示原因；Blob 409 可解析 detail。
2. 运行 `npx tsx --test test/reportRecovery.test.ts`，确认失败。
3. 同步 summary 类型，以后端恢复字段决定动作；复用 generate mutation；解析普通 JSON 与 Blob JSON detail。
4. 运行契约测试与 `npm run build`，转绿后提交 `feat: add historical report recovery controls`。

### Task 3: 全链回归与文档收口

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Test: `api-service/tests/test_rule_gates.py`

1. 运行历史报告定点与完整 rule gates。
2. 运行 GUI production build、compileall、diff-check。
3. 把 P1-53 标为 PR #346 完成，把 Current Focus 切到 P2-26 并记录验证事实。
4. 按 AGENTS.md 0.5 枚举列表、详情、下载、生成、单/多/缺执行、sanitized/legacy/非 MIMO 全集；功能 P1 修至 0。
5. 提交 `docs: ready P2-26 for review`。

### Task 4: Ready PR 与最多两轮外审

1. 推送分支，创建 Ready PR，触发 `@codex review`。
2. R1 核实并处理本片内意见，TDD 修复后触发最终 R2。
3. R2 无 P1 立即 merge；R2 有 P1 则修复、内审、回归后 merge，不触发 R3，并记录尾修未获外审覆盖。
