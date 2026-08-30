# BaseStation Mock Adapter Reload Guard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 BaseStation 型号从 UXM 切换为 CMW500（或反向切换）但 HAL 尚未重载时，于同步、就绪和执行冻结前明确拒绝旧 Mock adapter，并引导操作员安全重载 HAL。

**Architecture:** 保留“保存配置”和“重载全部仪器会话”两步式安全边界，不在保存时自动断开硬件。新冻结在 `resolve_base_station_binding()` 中核对 loaded Mock 与所选 adapter manifest；复用既有冻结时在纯 lock-time validator 中核对 loaded Mock 与 frozen adapter。最终 execution-evidence 安全门保持不变。GUI 仅延长 BaseStation 保存后的重载提示，不新增第二份配置真值。

**Tech Stack:** Python / FastAPI / SQLAlchemy / Pytest；React / TypeScript / Node test

---

### Task 1: Mock adapter 在共享 binding resolver 中 fail-loud

**Files:**
- Modify: `api-service/app/services/base_station_binding.py`
- Test: `api-service/tests/test_p2_44_base_station_binding_resolver.py`

1. 新增失败测试：冻结 CMW500 配置、loaded driver 为 UXM `MockBaseStation` 时，resolver 必须以包含“reload HAL”的可操作错误拒绝；反向 UXM 配置 + CMW Mock 同样拒绝。
2. 运行定点测试，确认旧实现错误放行。
3. 在 adapter registration 解析后，对 simulated driver 复用 manifest `adapter_id` 做精确相等核对；复用既有 configured simulated freeze 时对 frozen adapter 做相同核对，`diagnostic_unbound` 的空 adapter 保持原合同。不放宽 real validator，不修改 execution-evidence 最终门。
4. 运行 resolver、LabProfile sync、readiness、execution qualification 相关测试，确认共同入口一致 fail-closed。

### Task 2: 保存后的 HAL 重载提示可见且可执行

**Files:**
- Modify: `gui/src/App.tsx`
- Test: `gui/src/features/Equipment/baseStationModelPresetDraft.test.ts`

1. 新增失败测试：BaseStation 保存成功提示必须明确指向页面顶部“重新加载驱动”，且提示停留时间长于通用 2 秒反馈。
2. 运行 GUI 定点测试，确认旧实现失败。
3. 为 `showFeedback` 增加可选持续时间；BaseStation 保存使用较长提示，其他反馈保持原行为。
4. 运行 GUI 契约与 production build。

### Task 3: 验证、内审与交付

**Files:**
- Review: base-to-HEAD diff and every `resolve_base_station_binding()` consumer

1. 运行相关后端测试、规则门、GUI 契约、production build、compileall、单一 Alembic head 与 diff-check。
2. 运行全后端回归。
3. fresh 功能内审，功能 P1 归零后提交、推送并开 Ready PR。
4. 走 Codex R1→R2；覆盖最新 HEAD 的外审无 P1 后 merge，fetch 并 ff-only 同步本地 main，清理 worktree。
