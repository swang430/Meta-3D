# P0-5 SCPI Evidence Closure Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让一次正式 P0-5 TestExecution 可以追溯关键 SCPI 的手册依据、发送、回复、接受、生效状态和最终 attach/吞吐/转台结果。

**Architecture:** 采用 P0-5 垂直切片。HAL基类只补传输证据；F64、UXM、转台各自负责仪器语义；结构化摘要进入现有 TestExecution JSONB，原始往返继续进入 SCPI日志。

**Tech Stack:** Python 3、FastAPI、SQLAlchemy/PostgreSQL JSONB、React/TypeScript、pytest、现有诊断序列框架与结构化日志。

---

## 执行总序

严格按 `P1-45 → P1-46 → P1-41 → P1-47A → P1-47B → P1-47C → P0-5现场复验`，每片一个PR、WIP=1。

### Task 1：P1-45 现场项与载体映射

**Files:**
- Modify: `docs/roadmap-first-call.md`

1. 把 Blocked on hardware 表逐行核对到 GUI 可见的诊断序列或正式 TestCase。
2. 对没有载体的事项逐项 triage：只有 P1-46 已批准范围才并入；其余保留 Discovered/Blocked/HOLD，不写临时脚本替代。
3. 检查所有“当前队首”等快照措辞，改成指向 Current Focus。
4. 运行文档关键词和路线图一致性检查。
5. 走精简内审；docs-only 外审通过后合并。

### Task 2：P1-46 手册证据与缺失载体

**Files:**
- Modify: `api-service/app/diagnostics/sequences/uxm_scpi_compatibility.py`
- Modify/Create: `api-service/app/diagnostics/sequences/` 下经 P1-45 确认的剧本序列
- Test: `api-service/tests/test_uxm_scpi_compatibility.py`
- Test: 对应新增序列测试

1. 从 NotebookLM/手册逐条确认命令字面量和 Test Application 范围。
2. 写失败测试：IRAT 下 `TDD_PATTERN=None` 不得让序列恒失败；判定集必须与 `MAC_CFG_MANDATORY` 对齐。
3. 运行测试确认失败。
4. 最小修改判定集；没有 `confirmed` 手册证据的命令不得用于正式判绿。
5. 只为 ON 态同值写补剧本载体；inherit 层数因缺少实际生效观测手段，继续留在 Discovered 待评估池。
6. mock只验证序列不崩与判据分支，不声明真机通过。
7. 对“扩大命令适用范围”“onsite-observed/unverified判绿”分别做变异并确认测试变红。
8. 走全套内审和外审。

### Task 3：P1-41 UXM错误队列失控止血

**Files:**
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: `api-service/app/hal/uxm_command_profiles.py`
- Test: 新增定向错误队列测试

1. 从真实日志定位20万行循环的实际调用栈。
2. 用手册证据确定当前 Test Application 是否存在合法错误查询；未确认则不得猜命令。
3. 写失败测试：错误查询自身返回 `-113` 时循环必须有界且不能把自身错误无限排入。
4. 运行测试确认失败。
5. 实现最小上界/退出条件；不以日志轮转代替控制流止血。
6. 变异删除上界或恢复无限循环，确认测试变红。
7. 走全套内审和外审。

### Task 4：P1-47A SCPI传输证据配对

**Files:**
- Modify: `api-service/app/hal/base.py`
- Modify: `api-service/app/core/logging_config.py`
- Modify: `api-service/app/hal/aerotech_positioner.py`
- Test: `api-service/tests/test_scpi_log_evidence.py`
- Test: 对应 Aerotech socket 传输证据测试

1. 写失败测试：一次调用的TX与OK/RX/ERR必须共享非空 `exchange_id`，TX/OK必须带结构化command/query。
2. 写失败测试：`wait_for`超时和task取消必须各留一条终态证据并原样传播取消。
3. 运行测试确认失败。
4. 在公共 SCPI 调用入口生成 `exchange_id` 并透传现有日志helper；同时把活跃
   `RealAerotechDriver._send` socket 路径接入同一证据结构，禁止假设 `hal/base.py` 能覆盖转台。
5. 对 `asyncio.CancelledError` 单独记录后裸raise；普通异常控制流不变。
6. 保持空字符串、空白字符串、`not ready` 三种原始形态可区分。
7. 在进入日志前统一脱敏：IMSI 只允许哈希或末四位，认证参数/密钥禁止落日志；原始 SCPI 日志默认最多保留30天。
8. 运行定向测试；执行删除配对ID、让 `RealAerotechDriver._send` 绕过统一证据结构、吞掉取消、合并空字符串、取消脱敏/30天上限等变异并确认变红。
9. 最后运行全量测试，此后不再编辑；走全套内审和外审。

### Task 5：P1-47B 仪器接受/生效判据

**Files:**
- Create: `api-service/app/data/scpi_evidence/p0_5_commands.json`
- Modify: `api-service/app/hal/propsim_f64.py`
- Modify: `api-service/app/hal/uxm_base_station.py`
- Modify: 转台正式执行使用的驱动/执行器文件（开片时由P1-45映射确定）
- Test: 对应F64、UXM、转台定向测试
- Test: `api-service/tests/test_rule_gates.py`

1. 建立只覆盖P0-5关键命令的证据清单，写入NotebookLM来源ID、章节和适用范围。
2. 从真实连接自动采集仪器型号、固件版本、UXM Test Application；禁止用配置声明或人工填写替代。
3. 写规则门：关键命令集合必须被证据清单覆盖；只有与实际环境快照匹配的 `confirmed` 可以通过，`onsite-observed` / `unverified` 均不得判绿。
4. 运行门并做“删来源”“扩大LTE_NR_IRAT范围”“onsite-observed/unverified判绿”变异。
5. F64按写→OPC→错误队列→回读→STATE实现E2/E3摘要。
6. UXM把配置回读、APPLY、协议栈状态和业务结果分层；不得把配置回显直接写成E3。
7. 转台记录请求角、反馈角、容差和坐标系偏置。
8. 运行定向测试与全量测试；走全套内审和外审。

### Task 6：P1-47C TestCase持久化与展示

**Files:**
- Modify: `api-service/app/services/test_case_runner.py`
- Modify: `api-service/app/services/mimo_ota/executors/` 中产生关键控制/结果的执行器
- Modify: `api/openapi.yaml`
- Modify: `gui/src/types/api.generated.ts`（生成）
- Modify: TestExecution详情/报告相关GUI组件（开片时按活消费方定位）
- Test: TestCase执行、API契约、报告和GUI规则门测试

1. 写失败测试：正式执行必须把 `scpi_evidence` 摘要持久化到同一 TestExecution。
2. 摘要字段固定为 requested、command_sent、readback、exchange_ids、evidence_level、source_reference、verdict、reason；`exchange_ids` 按发生顺序关联原始往返。
3. 同一 TestExecution 固化真实连接采集的 instrument_model、firmware_version、uxm_test_application，不接受配置声明冒充。
4. 任何mandatory项为unknown/rejected、证据非confirmed或执行环境不匹配时，正式验收不得显示通过。
5. 按 OpenAPI → 生成类型 → 服务 → GUI 顺序接通展示。
6. GUI分别显示已发送/已接受/已生效/结果成立。
7. 报告明确区分直接证据、间接证据和未确认项；IMSI只显示哈希/末四位，认证信息绝不展示。
8. 做“删除一项证据仍显示通过”“断开exchange_ids关联”“完整IMSI/认证参数泄漏”的变异并确认测试变红。
9. 运行全量测试；走全套内审和外审。

### Task 7：P0-5现场正式复验

**Files:**
- Modify: `docs/roadmap-first-call.md`
- Modify: 对应现场结果文档

1. 出发前运行 P1-45/46 指定的全部诊断序列。
2. 从正式 TestCase 启动，不现场手敲SCPI、不使用临时脚本。
3. 核对UXM为RRC connected + bearer active；F64模型匹配且RUNNING。
4. 核对四个目标角在偏置补偿后反馈误差均≤±1°，且四个方向各自有有效正吞吐；不要求数值互不相同。
5. 从一个execution_id追溯全部关键exchange_id、环境快照和confirmed证据来源。
6. 失败、unknown、onsite-observed或unverified项保留未关闭状态；全部满足才关闭P0-5。
7. 现场证据由一名未参与执行的人复核后更新roadmap。

## 内外审交付模板

每次内审prompt必须包含：当前 `git diff --cached`、跑在当前staged版本上的测试输出、已跑变异清单，并声明全量测试后未再修改文件。P1-45用精简档；其余全部全套。内审主体必须是完整遵循 `.claude/agents/pre-commit-reviewer.md`、只审不改的独立 Codex subagent，主代理自审不能替代。外审由 GitHub `chatgpt-codex-connector[bot]` 承担，每次推送后用 `@codex review` 明确触发，270秒后查三通道，最多两轮；本地主代理审查不算外审，合并后做迟到回查。
