# P3-22 Test Contract Convergence Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 收敛已证明等价的 HAL 模式测试源码，同时保持全部产品契约 cell、断言和安全变异保护。

**Architecture:** 只修改测试与 roadmap 文档。用一张显式参数矩阵替代三组重复 class/fixture/test methods；不改 `_decide_use_real()` 或任何生产行为。

**Tech Stack:** Python 3.12, pytest, Git diff checks.

---

### Task 1: 固化基线与候选裁决

**Files:**
- Create: `docs/plans/2026-08-22-p3-22-test-contract-convergence-design.md`
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/plans/2026-08-21-roadmap-discovered-triage-design.md`

1. 记录测试文件/行数、全后端基线和三类候选。
2. 为每个候选写出产品故障，只有同 fixture、同路径、同断言语义的候选进入改动。
3. 将 P2-31 标为 PR #368 / merge `2c9d5ff` 完成，将 Current Focus 切到 P3-22。

### Task 2: 收敛 HAL 模式决策表

**Files:**
- Modify: `api-service/tests/test_hal_mode_force_mock.py`

1. 先保存当前 10 个决策 case 的 mode、输入、预期与测试名。
2. 用带稳定 id 的参数矩阵替代三组 fixture/classes；保留两个枚举测试。
3. 运行 `pytest --collect-only`，确认仍有 12 个测试结果。
4. 运行 focused 测试并执行真假方向变异，确认边界会红；恢复产品代码。

### Task 3: 回归、内审与收口

**Files:**
- Modify: `docs/roadmap-first-call.md`

1. 运行相关规则门、全后端、`compileall` 与 `git diff-check`。
2. fresh 内审核对：产品代码零改动、矩阵零缺 cell、被保留候选理由成立。
3. 将 P3-22 状态更新为本地完成，提交、推送并开 Ready PR；按仓库规则完成 Codex 外审与合并。
