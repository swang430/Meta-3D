# P0-5 SCPI 证据闭环设计

> 状态：2026-08-06 用户批准。正式开发按 `P1-45 → P1-46 → P1-41 → P1-47A/B/C` 执行，完成后进行 P0-5 现场正式复验。

## 1. 目标

现场已经完成 DUT attach 和转台四方向吞吐，证明物理链路可工作；但现有记录不能逐层证明关键 SCPI 已发送、被仪器接受、进入实际工作状态，并与最终业务结果属于同一次 `TestExecution`。本设计补齐这条证据链，证据不足时明确不通过，不把“现场有结果”直接等同于“软件完整流程正确”。

## 2. 方案选择

采用“P0-5 垂直闭环 + 最小公共能力”，不只补日志，也不建设覆盖所有仪器的通用证据平台：

- 公共层只负责 SCPI 往返配对、上下文和传输结果。
- UXM、F64、转台分别按自己的手册语义判断接受/生效。
- 诊断序列验证命令支持与状态能力；正式验收仍由 TestCase 驱动。
- 第一阶段不增加新数据库表；摘要存入 `TestExecution.config["scpi_evidence"]`，原始往返留在结构化 SCPI 日志。

## 3. 五级证据模型

| 级别 | 名称 | 判据 |
|---|---|---|
| E0 | Intent | 程序产生了准备发送的命令 |
| E1 | Transport | 得到 OK/RX，或明确记录 ERR/timeout/cancelled |
| E2 | Accepted | 手册支持的错误检查、精确回读或状态判据证明仪器接受 |
| E3 | Applied | APPLY 后协议栈/仿真状态、模型状态或位置反馈符合预期 |
| E4 | Outcome | DUT attach、吞吐、转台到位等最终业务结果成立 |

任何步骤只能申报它实际达到的最高等级。`*OPC? == 1` 只代表操作完成；普通配置回读若手册未说明其口径，不得直接申报 E3。

## 4. SCPI 手册证据清单

为 P0-5 的关键命令维护机器可检查的证据清单。每项包含：仪器、Test Application/固件适用范围、精确命令模板、用途、来源 ID、手册章节、可证明等级、配套回读和 `confirmed | unverified | onsite-observed` 状态。

规则门要求：

1. 正式闭环所用关键命令必须有证据项。
2. 当前 Test Application 必须落在证据声明的适用范围内。
3. 只有 `confirmed` 手册证据可以支撑正式判绿；`onsite-observed` 只记录现场事实，不能替代手册适用范围，`unverified` 同样不得判绿。
4. 删除来源、扩大适用范围，或让 `onsite-observed` / `unverified` 通过时，变异测试必须变红。

证据范围不能依赖配置声明或人工填写。每次正式执行开始时必须从真实连接自动采集并固化
仪器型号、固件版本和 UXM Test Application，随后用这份同次执行快照匹配证据清单的适用范围。

## 5. NotebookLM 实证边界

### F64 / PROPSIM

Notebook：`982222b7-4953-46cd-9949-00fa97882353`。

已由手册原文确认：

- `DIAGnostic:SIMUlation:STATE?`：运行状态。
- `DIAGnostic:SIMUlation:MODel:STATE?`：当前模型/CIR/仿真时间。
- `INPut:MEASure:STATus:GET?` 与 `INPut:MEASure:RESult:GET?`：输入测量状态和结果。
- `OUTPut:MEASure:RESult:GET?`：输出结果未就绪时返回 `not ready`。
- `*OPC?`：等待挂起操作完成，但不证明无设备错误。
- `SYSTem:ERRor?`：读取错误队列。
- 手册 §20.6.1.1 明确示范写参数后用对应 query 回读。

严格边界：输入/输出测量查询返回空字符串时的语义，手册均未说明；不得自动解释成 `not ready`。

### UXM

Notebook：`236d9621-e3ce-4ed1-a8e1-7819b674dbcd`。

已由手册原文确认：多数配置在小区 ON 时必须执行 APPLY 才进入协议栈；普通配置查询在 APPLY 前后代表缓存还是实际生效值，手册没有通用保证。

严格边界：`SYSTem:ERRor[:NEXT]?` 的手册适用范围只明确为 `NSA | SA`；现有来源未确认 `LTE_NR_IRAT` 可用的带问号错误队列查询。P1-46 必须把这一项保持为 `unverified`，除非找到明确覆盖当前 Test Application 的手册原文。禁止现场猜命令拼写。

## 6. 公共传输证据

现有 TX/OK/RX/ERR 增加同一次调用共享的 `exchange_id`，并统一携带 `execution_id`、`instrument_id`、结构化 command/query、方向、耗时和结果类型。公共 SCPI helper 与活跃的 `RealAerotechDriver._send` socket 路径都必须接入；不能假设 HAL SCPI 基类自然覆盖转台。

必须区分：

- transport exception
- timeout
- cancelled
- empty response
- whitespace-only response
- `not ready`
- device rejected

取消/超时记录后原样重新抛出，不改变现有控制流。

原始留痕在进入日志前必须脱敏：IMSI 只允许哈希或末四位，认证参数及密钥不得进入证据或日志。
原始 SCPI 日志默认保留 30 天并受轮转上限约束；数据库不复制原始往返，只保存结构化摘要。

## 7. 仪器闭环

### F64

关键写操作采用：写入 → `*OPC?` → `SYSTem:ERRor?` → 对应参数回读 → 仿真/测量状态。至少覆盖模型、中心频率、输入参考/crest、输出增益/损耗、直通/衰落状态和 RUNNING 状态。

### UXM

采用：写配置 → 手册确认的命令级回读 → APPLY → 操作完成 → 小区协议栈状态 → DUT连接状态 → KPI/吞吐结果。配置查询一致只算 E2；APPLY 后状态与业务结果才支持 E3/E4。没有直接回读的 MAC 配置明确标记为间接验证。

### 转台

记录请求角、下发指令、反馈角和容差。当前已知命令角与反馈角存在约 90° 系统偏置；四方向覆盖成功不能替代绝对角度校准结论。

## 8. TestCase 与持久化

- 诊断序列负责命令支持、状态和回读能力，不代替正式测试。
- 正式 TestCase 在同一个 `execution_id` 下产生 `scpi_evidence` 摘要。
- 执行快照保存从真实连接自动采集的 instrument_model、firmware_version、uxm_test_application。
- 摘要逐项保存 requested、command_sent、readback、exchange_ids、evidence_level、source_reference、verdict、reason；`exchange_ids` 按发生顺序关联到原始往返。
- 执行状态 FastAPI response schema/endpoint 必须读回脱敏摘要，不能让持久化字段保持 write-only。
- `ReportDataCollector` → `ReportData.to_dict()` → `ReportService` → 活跃 PDF 渲染器必须逐层传递并展示证据。
- `DiagnosticRun.output_excerpt` 只作人读摘要；2KB 截断内容不作为正式原始证据。
- GUI/报告分别显示“已发送、已接受、已生效、结果成立”，不压缩成一个模糊成功标记。

## 9. 正式验收

P0-5 只有同时满足下列条件才能关闭：

1. 关键命令都有与同次执行环境快照匹配的 `confirmed` 手册证据；其它状态一律非通过。
2. SCPI 往返可由 `execution_id + exchange_id` 完整配对，摘要逐项保存对应 `exchange_ids`。
3. UXM 达到 RRC connected + bearer active；F64 当前模型匹配请求且状态为 RUNNING。
4. 转台完成坐标偏置补偿后，四个目标角的请求角/反馈角误差均 ≤ ±1°。
5. 四个方向各自返回有效且大于零的吞吐；不要求四个数互不相同。
6. 全流程从正式 TestCase 启动，不依赖临时脚本或现场手敲 SCPI；IMSI/认证信息满足脱敏规则，原始 SCPI 日志留存上限为30天。

## 10. 内审与外审

每个切片单独提交、单独审查，WIP=1：

| 切片 | 内审档位 | 审查重点 |
|---|---|---|
| P1-45 | 精简 | 映射完整性、状态是否陈旧、无代码机制 |
| P1-46 | 全套 | 手册原文、Test Application适用范围、诊断判绿条件 |
| P1-41 | 全套 | 循环上界、错误命令、自身错误查询再次入队、速率/体量 |
| P1-47A | 全套 | exchange配对、并发、取消、超时、异常原样传播 |
| P1-47B | 全套 | E2/E3语义、UXM/F64差异、禁止把回显当生效 |
| P1-47C | 全套 | TestCase契约、持久化、GUI/报告不假绿 |

每片在最终全量测试后不再改文件，把 staged diff、当前版本测试输出和已跑变异清单交给
**独立 Codex subagent**；它必须完整遵循 `.claude/agents/pre-commit-reviewer.md`，只审不改，
主代理自审不能替代。推送后用 `@codex review` 触发 GitHub
`chatgpt-codex-connector[bot]` 外审，270秒后检查 reviews、inline comments、issue comments
三通道；本地主代理审查不算外审，最多两轮。合并后再做迟到回查，迟到真问题开新分支。
