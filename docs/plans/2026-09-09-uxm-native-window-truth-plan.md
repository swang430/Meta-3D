# UXM 原生有限窗口现场诊断实施计划

> 执行方式：主 agent 顺序实施，严格 RED → GREEN；每个任务完成后做相关回归。

## Task 1：定义失败合同与手册边界

**文件：**

- 新增 `api-service/tests/test_p2_52_uxm_native_window_truth.py`
- 修改 `api-service/app/hal/uxm_command_profiles.py`

1. 写测试证明：新序列和新 profile 常量尚不存在时失败；确认缺失、参数非法、方言错误、
   Mock 或未连接时零写命令。
2. 实跑 RED，记录失败来自缺模块/缺常量，而不是 fixture 错误。
3. 只为 `LTE_NR_IRAT` 增加带精确手册锚点和范围错位说明的 Length/Continuous 写形；
   其他 profile 保持 `None`。
4. 实现最小 metadata、参数和写前门，让零写合同 GREEN。

## Task 2：实现两窗口行为观察

**文件：**

- 修改 `api-service/tests/test_p2_52_uxm_native_window_truth.py`
- 修改 `api-service/app/diagnostics/sequences/uxm_native_window_truth.py`

1. 写两窗口正常路径 RED：校验 Clear/Off/Length/Single/On 的精确顺序、每条 I/O 后错误
   归属、progress 精确到界、settle 样本、第二窗口重新起算，以及最终仍
   `formal_verdict=unverified`、`success=false`。
2. 实现同步/异步安全 I/O、错误解析、progress 解析和有界轮询；不使用 `STATe?` 或
   `*OPC?`。
3. 写并修复写拒绝、畸形、回退、越界、超时、第二窗口继承等失败路径。

## Task 3：收尾、安全和生产隔离

**文件：**

- 修改 `api-service/tests/test_p2_52_uxm_native_window_truth.py`
- 修改 `api-service/app/diagnostics/sequences/uxm_native_window_truth.py`

1. 写异常和取消 RED，证明尝试过写入后一定发送 `STATe 0`、归属 cleanup 错误，且同步
   I/O 未结束前不传播取消。
2. 实现 `finally` cleanup；保留 raw，不把 cleanup 或外层 lease release 伪装成正式证据。
3. 增加源码/消费方门，证明新诊断常量不进入正式 measurement、execution、report、KPI。

## Task 4：更新活文档与旧计划的未来指引

**文件：**

- 修改 `docs/roadmap-first-call.md`
- 修改 `docs/plans/2026-08-30-p2-52-uxm-window-boundary-evidence.md`

1. blocker 与 U-13 指向 checked-in `uxm_native_window_truth`，明确代码载体完成但现场证据
   仍阻塞。
2. 将旧计划 §6 标为被 2026-09-09 受控序列取代；不改写历史验证与当时事实。

## Task 5：验证、审查与交付

1. 运行 P2-52 专项、诊断序列合同、rule gates 和受影响链。
2. 运行全后端、`compileall`、单一 Alembic head、base-to-HEAD diff-check。
3. 逐文件 fresh 功能内审，重点检查：错误队列归属、取消/cleanup、第二窗口继承、正式
   消费隔离和文档镜像；P1 必须为 0。
4. 提交、推送、创建 Ready PR，执行 Codex R1；修复功能 P1 与本片内 P2 后触发 R2。
5. 覆盖最新 HEAD 的 R2 无 P1且 mergeable/checks 通过或无必需 checks 时合并；否则只
   继续处理 P1 至最新 HEAD 无 P1。
6. fetch 验证 `origin/main`，本地主目录 `ff-only` 同步，保留未跟踪仪器资料，清理本片
   worktree 和本地分支。
