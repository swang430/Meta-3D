# NEW-1 F64 Active Output Set Implementation Plan

> **For Codex:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 让 F64 输出电平窗口诊断只核查当前仿真权威回读的活动物理输出口，避免未配置口把合法检查误判为未确定。

**Architecture:** 在现有只读诊断序列内按厂商手册实时遍历仿真拓扑，用 `MODEL:INFO?` 输出数量交叉核对各组输出口并集。只有完整实时拓扑能进入逐口检查；人工口集、缓存和整机通道数都不能授予 SUCCESS。

**Tech Stack:** Python 3.12、FastAPI diagnostics protocol、pytest、Keysight PROPSIM ATE/SCPI。

---

### Task 1: 锁定现场故障的 RED

**Files:**
- Modify: `api-service/tests/test_p1_65_propsim_f64_output_level_windows.py`

**Step 1:** 新增冷缓存场景：`SYSTem:INFO?` 报 32，但实时 `MODEL:INFO?` / group 输出只含 16 口；断言只查询这 16 口并能 SUCCESS。

**Step 2:** 新增旧缓存 32 口场景：实时拓扑仍为 16 口；断言缓存不能覆盖实时回读。

**Step 3:** 新增人工 `outputs` 参数不能缩小活动集合的边界，并运行专项测试确认 RED。

### Task 2: 最小 GREEN 实时拓扑解析

**Files:**
- Modify: `api-service/app/diagnostics/sequences/propsim_f64_output_level_windows.py`

**Step 1:** 新增有界的正整数 CSV / `MODEL:INFO?` / group 输出解析，所有原始回复继续进入 step 审计。

**Step 2:** 删除通道数兜底与人工口集授权；每次运行读取实时 group 输出并集并与模型输出数核对。

**Step 3:** 只遍历实时活动口；拓扑未知时在任何逐口查询前返回 `UNDETERMINED`。

**Step 4:** 运行 Task 1 专项测试确认 GREEN。

### Task 3: 补齐状态与失败路径

**Files:**
- Modify: `api-service/tests/test_p1_65_propsim_f64_output_level_windows.py`
- Modify: `api-service/app/diagnostics/sequences/propsim_f64_output_level_windows.py`

**Step 1:** RED 覆盖输出数量矛盾与非连续口号；复用既有缺失回复/查询异常用例证明拓扑未知时不会进入逐口查询。

**Step 2:** 最小 GREEN；任一拓扑失败均不发逐口命令，错误队列仍按现有契约收尾。

**Step 3:** 运行专项与 F64 topology/diagnostic 相关回归。

### Task 4: 同步现状文档

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: `docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md`

**Step 1:** 把 NEW-1 标为本地半完成、现场 SUCCESS 复验仍开放。

**Step 2:** 全仓搜索旧的“32 口一刀切”和人工口集口径，确认没有与新行为冲突的未来承诺。

### Task 5: 验证、内审与交付

**Files:**
- Test: `api-service/tests/test_p1_65_propsim_f64_output_level_windows.py`
- Test: F64 diagnostics/topology 受影响集合
- Test: `api-service/tests/test_rule_gates.py`

**Step 1:** 运行专项、受影响链、规则门、全后端、compileall、单一 Alembic head、diff-check。

**Step 2:** fresh 独立内审，按 P1/P2/P3 分栏；P1 清零后才提交。

**Step 3:** 提交、推送、Ready PR；Codex R1 处理本片 P1/P2 后触发 R2，R2 无 P1 即合并。

**Step 4:** fetch 验证 `origin/main`，主目录 ff-only 同步，清理工作树/本地分支；NEW-1 现场复验保持开放，然后启动 P2-42。
