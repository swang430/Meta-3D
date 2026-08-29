# P2-47 BaseStation 结构化 Attach Receipt Implementation Plan

> **For Codex:** 按 `executing-plans` 逐 Task 执行；每个 Task 先 RED，再做最小 GREEN，不跨到 P2-48。

**Goal:** 把 BaseStation Attach 从厂商含义不同的布尔值收敛为 execution-bound 四阶段 receipt，使诊断
继续与正式证据强度分离。

**Architecture:** 在既有 `BaseStationDriver` 增加权威 `attach()` 返回不可变 receipt；旧
`start_signaling()` 仅作兼容投影。CMW500/UXM 复用现有命令和回读，MEASURE 与 P2-43 evidence writer
消费共同 receipt；历史 execution 缺新字段时保持历史兼容，新 execution fail-closed。

**Tech Stack:** Python 3.13、dataclasses、Pydantic v2、pytest、现有 SCPI evidence capture。

---

## Task 1：定义四阶段 Receipt 与兼容入口

**Files:**

- Modify: `api-service/app/hal/base_station.py`
- Create: `api-service/tests/test_p2_47_base_station_attach_receipts.py`

**RED:** 锁定四阶段全集/唯一顺序、requested/applied/status/evidence 不变量、confirmed false 与 unknown
区分、authoritative confirmed 必须有 exchange id、terminal stage、diagnostic/formal 派生、不可变性和
Mock simulated unknown。证明对象不能被隐式当 bool。

**GREEN:** 增加 `BaseStationAttachStageReceipt` / `BaseStationAttachReceipt`；BaseStationDriver 新增抽象
`attach()`，`start_signaling()` 只投影 receipt 的 diagnostic 继续判据；Mock 返回 simulated receipt。

**Verify:** 新测试 + `test_p2_43_base_station_receipts.py`。

**Commit:** `feat: define structured base station attach receipt`

## Task 2：映射 CMW500 现有权威阶段

**Files:**

- Modify: `api-service/app/hal/cmw500_base_station.py`
- Modify: `api-service/tests/test_p1_73b_cmw_state_machine.py`
- Create: `api-service/tests/test_p2_47_cmw_attach_receipt.py`

**RED:** 成功精确映射 CELL/ATTACHED/CONNECTED；RRC unavailable；各失败/错误队列/超时/取消只保留本次
已确认事实；confirmed authoritative stage 带直接 exchange id；兼容 `start_signaling()` 仍返回 bool。

**GREEN:** 将既有序列收进 `attach()` 的同次 capture，局部记录阶段，不新增命令；旧入口调用新入口。
保留 timeout 恢复与 shielded SAFE cleanup。

**Verify:** CMW state machine、integration、P2-47 CMW 定点。

**Commit:** `feat: map cmw attach stages to receipt`

## Task 3：映射 UXM 与 Mock 的保守阶段

**Files:**

- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/tests/test_p02_uxm_truth_source.py`
- Create: `api-service/tests/test_p2_47_uxm_attach_receipt.py`

**RED:** connected-like 只给 diagnostic terminal RRC，registration/cell 不被错误升级，data bearer unavailable；
IDLE/枚举外/超时保持未达到或 unknown；fallback 不升级；Mock 无 confirmed stage。

**GREEN:** 复用现有 status poll/parser 与 capture，将 manifest strength 精确复制到 receipt；不新增命令或
扩大状态枚举。

**Verify:** UXM truth source/config tests、Mock receipt tests。

**Commit:** `feat: map uxm attach truth conservatively`

## Task 4：把 Receipt 绑定 execution attempt/lease/session

**Files:**

- Modify: `api-service/app/services/mimo_ota/base_station_execution_evidence.py`
- Modify: `api-service/app/services/execution_scpi_evidence.py`
- Modify: `api-service/tests/test_p1_73c_base_station_execution_evidence.py`
- Create: `api-service/tests/test_p2_47_base_station_attach_evidence.py`

**RED:** writer 接受两家同形 receipt；拒绝 attempt/lease/session/adapter/evidence drift、重复写、无 exchange
的 authoritative confirmation；新 evidence 显式空列表，历史缺字段严格往返；新 formal envelope 缺/弱
Attach receipt fail-closed，历史保持兼容。

**GREEN:** 增加 attach operation Pydantic envelope 与 writer；初始化/parse/formal envelope 做 presence-aware
兼容，不读当前状态回填历史。

**Verify:** P1-73C evidence/formal consumers、P2-45 qualification/site certification。

**Commit:** `feat: persist execution-bound attach evidence`

## Task 5：迁移 MEASURE 与全部共同消费点

**Files:**

- Modify: `api-service/app/services/mimo_ota/executors/measure.py`
- Modify: `api-service/app/services/mimo_ota/executors/precheck.py`（仅当新结构已有直接消费入口）
- Modify: `api-service/tests/test_attach_milestones.py`
- Modify: `api-service/tests/test_p1_47c_execution_scpi_evidence.py`
- Modify: `api-service/tests/test_p1_32_mac_config_skip.py`
- Create: `api-service/tests/test_p2_47_measure_attach_receipt.py`

**RED:** MEASURE 必须调用 `attach()`、先持久化 receipt 再决定是否继续；错误指出 terminal stage/evidence；
Mock/unknown 不生成正式绿色；formal runner 与 commissioning 四入口没有旁路；生产 MEASURE 不再调用
`start_signaling()`。

**GREEN:** 使用共同 receipt 和 writer；里程碑投影结构化 stage truth，旧 `rrc_connected` 只作明确兼容
镜像；诊断序列可继续用兼容入口。

**Verify:** attach milestones、MEASURE、commissioning/session、P2-42、P2-45 consumers。

**Commit:** `refactor: consume structured attach receipt`

## Task 6：生产门、Roadmap 与完整验证

**Files:**

- Modify: `api-service/tests/test_rule_gates.py`
- Modify: `docs/roadmap-first-call.md`
- Modify: P2-47 设计/计划（只同步实际实施结果，不扩大批准范围）

**RED/GREEN:** 增加门：生产 MEASURE 禁止 `start_signaling()`；receipt stages 必须与 manifest 四阶段全集一致；
正式 envelope 必须消费 execution-bound attach evidence。测试门发现严重度上限 P2。

**Focused:** P2-47、CMW/UXM state、attach milestones、P2-42/43/45、formal consumers、rule gates。

**Full:** 全后端；compileall；单一 Alembic head；base-to-HEAD diff-check。若未改 GUI/OpenAPI，明确不运行
其契约/build。

**Fresh review:** 按 AGENTS.md 0.5 再列全集，缺陷与建议分栏；功能 P1=0 后提交、推送、Ready PR，执行
Codex R1→R2。覆盖最新 HEAD 的 R2 无 P1才 merge commit；R2 若仍有 P1，最小修复并继续 P1-only
复审。合并后同步本地 main、保留未跟踪仪器资料、清理 worktree/分支，再开始 P2-48。

**Commit:** `test: close structured attach receipt contract`
