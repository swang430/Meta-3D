# P2-29 实施计划

工作树：`.worktrees/p2-29-model-load-evidence`，分支 `codex/p2-29-model-load-evidence`，基线 `7474893`（main, P1-57 合并后）。

## Task 1：RED 行为门
- Create `api-service/tests/test_p2_29_model_load_evidence.py`：
  ① ASC/B2 wire 形态窗口（FILE runtime .smu → OPC → ERR → MODEL:STATE? → STATE?=STOPPED）
    走真 `record_f64_command_capture` + 真 `PropsimF64Driver.build_p0_5_command_evidence`
    → APPLIED + formal_acceptance=True；
  ② 缺 STATE? 的窗口 → 不到 APPLIED（fail-closed 回归）；
  ③ 驱动源码门：ASC/B2 成功分支两条探针都在 `_readback_topology()` 之前；
  ④ measure.py 源码门：归档条件不再含 `GCM_NATIVE`。
- 运行确认 ③④（和 ①若探针影响 wire 断言）RED。

## Task 2：GREEN
- `propsim_f64.py`：ASC/B2 成功分支各加两条探针（锁内，注释引 AN §2.1/UR §20.4.3.14 与本设计）。
- `measure.py`：条件改 hasattr-only + 注释镜像同步。

## Task 3：变异 + 回归 + 交付
- 变异：删 ASC 探针 / 删 B2 探针 / 条件改回 GCM-only，各自让门红（实跑）。
- 回归：`test_p2_29_* + test_p1_47c_execution_scpi_evidence.py + test_p1_47a/b + test_rule_gates.py`；compileall；diff-check。
- roadmap/设计稿状态收口 → fresh 内审（全套档）→ PR → 外审（Gemini，Codex 额度尽）→ 合并。
