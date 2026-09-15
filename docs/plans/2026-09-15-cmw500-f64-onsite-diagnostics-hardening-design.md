# CMW500 + F64 现场诊断加固设计

## 目标

为下一轮 CMW500 + PROPSIM F64 现场调试收窄单步入口：保留现有受控诊断序列，补齐 F64 查询原始证据，消除 Local handback 的默认假值，并删除已经被产品路径替代或依赖已拆除架构的脚本。

## 可观察故障

1. `propsim_f64_health` 只保存 `SYST:ERR?` 的分类结果，目标查询（尤其 `MMEM:CDIR?` / `MMEM:CAT?`）的原始回复被丢弃，导致 P2-71 只能说“命令可能受支持”，不能复核仪器实际返回。
2. `SequenceRunnerPanel` 会把无默认值的 boolean 参数初始化为 `false`。`propsim_f64_local_handback_check` 因而能出现“观察文字写已回 Local，但结构化布尔仍为 false”的矛盾现场记录。
3. 三支脚本已经失去合法载体：旧 F64 资产硬表可覆盖服务器真值；旧吞吐脚本通过全局 TestCase 差集猜新会话并二次 PATCH；queue 清理脚本调用已拆除的 `/test-plans/queue` 架构。

## 全集与边界

### 参数产生与消费

- 产生方：各 `app/diagnostics/sequences/*.py::metadata.params_schema`。
- 服务投影：`app/diagnostics/loader.py::list_sequences` → `app/api/diagnostic_sequence.py::SequenceParamSpec`。
- GUI 类型与初始化：`gui/src/api/diagnosticService.ts`、`SequenceRunnerPanel.tsx`。
- 运行消费：`runDiagnosticSequence` 原样传入 `params`，各序列自行 fail-loud 校验。

在现有浅 schema 上增加可选 `choices: [{value, label}]`。它只约束 GUI 输入，不代替序列端校验。CMW probe 的 `sample`、handback 的 `phase` 与 Local/Remote 观察结论使用下拉框；其他数字、布尔、自由文本维持原行为。

### F64 原始证据

`propsim_f64_health` 不新增、不删除、不改写任何 SCPI 字面量。每个 Phase A 项保存：

- 目标 query 原文；
- 目标 raw reply（无回复为 `null`，空回复为 `""`）；
- 目标 query 异常（如有）；
- `SYST:ERR?` raw reply 与解析后的 code/text；
- 既有 status 与 critical 分类。

所有项目进入 `extra.scpi_observations`，即使 GUI 选择隐藏普通 SUPPORTED step 也不丢证据；可见 step 的 `raw` 使用目标 raw reply。现有 `*CLS`、错误队列消费、副作用警示和判决逻辑保持不变。

### Local handback

GUI 不再公开 `operator_confirmed_local: boolean`，改为必须显式选择的 `operator_local_state: "local" | "remote"`，默认空值。confirm 阶段：

- 未选择 → `UNDETERMINED`；
- `local` → `SUCCESS`；
- `remote` → `BLOCKER`；
- 其他值 → `ABORTED`，且不发送 SCPI。

为兼容已有 API 调用，后端仍接受旧 `operator_confirmed_local`，但 metadata 不再向 GUI暴露；持久证据同时写入新状态和由其派生的旧布尔字段。观察文字仍为必填，人工证据不会升级为正式资格。

## 脚本处置

- 保留 `scripts/onsite-f64-control.py`：它只调用已受控的控制权和 `.smu` 加载 API。
- 删除 `scripts/onsite-fix-f64-scenario-assets.py`：由服务器 `/channel-assets/vendor-files/smu-scan` 与同步链取代。
- 删除 `scripts/onsite-run-channel-throughput.sh`：由 `CreateSessionRequest.channel_asset_id`、TestCase 编辑与正式执行链取代。
- 删除 `scripts/cleanup-test-queue.py`：依赖的执行队列路由已拆除。
- 历史现场记录保持原样；仅修正当前代码注释、当前 README 与仍在生效的契约清单。

## 现场顺序

新 runbook 明确：先实机身份/配置完整性，再在独占维护窗口运行 F64 license、active-output window 与必要的 health；随后分别运行 CMW `tm1_one`、`tm3_two`；FDD 基线稳定后才进入 TDD；结束时 release → 人眼观察 → confirm。每一步记录 `diagnostic_run_id` / `execution_id`，诊断结果不替代 calibration、site certification、DUT attach 或正式 KPI 资格。

## 不做

- 不新增一键硬件编排器。
- 不新增、猜测或试探任何 SCPI。
- 不改变正式 provenance 白名单、qualification 或 KPI 判据。
- 不把 persisted `connected` 当作现场 live 连接证据。
- 不尝试关闭 P2-71 的设备字节摘要、版本管理或回滚半项。
