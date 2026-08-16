# P1-50 Retention Alert Isolation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 留存清理失败告警保持运维可见，同时绝不重新打开刚关闭的执行日志或泄漏文件描述符。

**Architecture:** 在真实根 logger + ExecutionFileHandler 路径上用测试复现回流。生产修复只在发留存失败 WARNING 的同步窗口内把 `current_execution_id` 置为 `-`，并用 ContextVar token 在 finally 恢复。

**Tech Stack:** Python logging、contextvars、pytest、unittest.mock。

---

### Task 1: 建立根 logger 回流 RED

**Files:**
- Modify: `api-service/tests/test_p1_40_execution_logs.py`

**Step 1: 写执行级回归**

在 `TestExecutionLogRetention` 增加测试：创建 handler、挂到 root、为 `current-exec` 打开流；
制造过期文件并 patch `Path.unlink` 抛 `OSError`；保持当前 execution context 调用
`close_execution("current-exec")`。

断言：告警可由 caplog 看到；`current-exec` 不在 `active_execution_ids()`；`_streams` 为空；
调用后 `current_execution_id` 仍是 `current-exec`。

**Step 2: 运行并确认 RED**

```bash
cd api-service
PYTHONPATH=. /Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_p1_40_execution_logs.py -k cleanup_failure_does_not_reopen
```

Expected: active 集合仍含 `current-exec`，测试失败。

**Step 3: 提交 RED**

```bash
git add api-service/tests/test_p1_40_execution_logs.py
git commit -m "test: reproduce P1-50 retention alert feedback"
```

### Task 2: 最小隔离留存失败告警

**Files:**
- Modify: `api-service/app/core/logging_config.py`

**Step 1: 替换错误注释与告警调用**

在 `_module_logger.warning()` 外使用：

```python
token = current_execution_id.set("-")
try:
    _module_logger.warning(...)
finally:
    current_execution_id.reset(token)
```

注释明确：模块 logger 仍传播，ContextFilter 会读取 contextvar；隔离的是执行关联，不是告警本身。

**Step 2: 运行定点测试并确认 GREEN**

Run 同 Task 1；Expected: passed。

**Step 3: 运行留存全集**

```bash
cd api-service
PYTHONPATH=. /Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_p1_40_execution_logs.py
```

Expected: 17 passed。

**Step 4: 提交生产修复**

```bash
git add api-service/app/core/logging_config.py
git commit -m "fix: isolate retention cleanup alerts from executions"
```

### Task 3: Roadmap、完整验证与审查闭环

**Files:**
- Modify: `docs/roadmap-first-call.md`

**Step 1: 更新实现状态**

把 P1-50 更新为实现完成待审，关闭对应 Discovered 当前态；保持 WIP=1。

**Step 2: 完整验证**

```bash
cd api-service
PYTHONPATH=. /Users/simon/Tools/MIMO-First/api-service/.venv/bin/pytest -q \
  tests/test_p1_40_execution_logs.py tests/test_rule_gates.py
cd ..
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m compileall -q api-service/app
git diff --check origin/main...HEAD
```

Expected: 零失败、零编译/whitespace 错误。

**Step 3: 内审**

按 AGENTS.md 枚举初始化/收尾两条 purge 入口、唯一告警写点、根 handler 消费、上下文恢复、
active 状态与 fd 生命周期；P1 清零后创建 Ready PR。

**Step 4: 两轮外审与合并**

R1 处理本片可执行意见，随后 R2；R2 无 P1立即 merge。R2 若仍有 P1，修复并内审/回归后
merge，不触发 R3。合并后自动创建 P1-51 独立分支并开始设计，维持 WIP=1。
