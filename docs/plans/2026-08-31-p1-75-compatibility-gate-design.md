# P1-75 — TestCase × BaseStation Adapter 执行兼容性硬门 设计稿

**日期**：2026-08-31
**状态**：设计稿，供 review
**Roadmap**：P1-75（当前非现场 WIP；总体边界见
`docs/plans/2026-08-30-base-station-testcase-compatibility-roadmap-design.md`）

## 1. 可观察故障（本片唯一要修的那一个）

HAL Mock 模式下，selected model / LabProfile binding / loaded adapter 全部一致指向 UXM，
但 `primary_carrier.radio_technology=lte` 的 CMW500 TestCase 仍完成执行并生成诊断报告。
execution `7ae66c69-edc5-422e-8681-d8ad56c23e64` 的冻结证据同时含 `adapter=uxm`、
UXM manifest `rats=[nr5g]`、requested `radio_technology=lte` —— 自相矛盾的证据被完整持久化，
系统没有在任何一步说"这个组合逻辑上不可能"。

**根因**：现有冻结（`freeze_base_station_adapter_profile`）只校验 model / binding / driver /
endpoint / transport 一致性，**从不读 TestCase 的结构化需求**。真实驱动的后置 RAT 拒绝
（`base_station.py:1426` `apply_requested_config`）发生在 connect 之后，且 MockBS 的
`get_supported_technologies()` 无条件返回双 RAT 并集（`base_station.py:2316`）把它绕空。

## 2. 实证前置

- **memory**：已查（判据不得读名称 / 验证打真实生效端 / 改前列全集 / ⑦）。
- **NotebookLM**：**显式不适用** —— 本片零新增 SCPI、不断言任何仪器语义；判据只消费
  已注册 manifest 的结构化声明与 TestCase 的结构化字段。条目原文写死"不得新增或猜测
  任何仪器命令"。

## 3. 域枚举（AGENTS.md 0.5：产生方 / 消费方 / 入口 / 历史 / 失败路径）

| 项 | 真值 |
|---|---|
| requested RAT 产生方 | TestCase `configuration.primary_carrier.radio_technology`（`schemas/mimo_ota/config.py:153`，`Literal["nr5g","lte"]`，默认 `nr5g`） |
| manifest 判据源 | `resolve_base_station_binding(...).manifest`（注册 manifest；UXM 声明 `rats=("nr5g",)`、CMW 声明 `rats=("lte",)`）。**不是** driver 自报的 `get_supported_technologies()` |
| 执行入口（全集，共 2 个） | ① `test_case_runner.py:271`、② `commissioning.py:1660` —— 都调 `freeze_execution_base_station_adapter_profile`，**一个门同时守两个入口** |
| 拒绝语义 | freeze 内 raise → runner 捕获为 `CaseNotExecutable` → rollback → 不排后台。此时零 connect、零 SCPI、零 phase progress、零报告 —— 恰是条目要求 |
| 冻结后漂移复核站点 | `measure.py:834` 的 `resolve_base_station_execution_plan` live 复核处（lease 后、首次 I/O 前）——本片把 compatibility 复核挂进同一站点 |
| resolution 三态 | `configured`(cmw500+profile) / `not_applicable`(uxm) / `diagnostic_unbound`(simulated 且无 adapter)。前两态都有 manifest **必须对账**；`diagnostic_unbound` 无 adapter 无 manifest —— 不存在"组合"，无从谈逻辑不可能，verdict 记显式 `no_adapter` 并保持现有放行（这是「模拟诊断无绑定」的既有语义，不是本片放宽的） |
| required operations 真值源 | measure 执行链经共同 SPI 实际调用的操作 → manifest token：`config`（set_cell_config）、`cell_attach`（attach 链）、`measurement_window`（measure_base_station_window）、`safe_idle_release`（cleanup/release）、`identity`（身份校验）。两家注册 manifest 今天都声明这 5 个 —— 现状全放行，门守的是**未来 adapter 漏声明** |
| 历史数据 | 旧 execution 的 frozen dict 无 compatibility 字段。**历史读取路径不回填不猜测**：证据消费按既有规则读，缺字段=当时未评估（P2-66 再收口终态语义） |

## 4. 方案

### 采用：纯判定器 + 两站点消费（freeze 拒入 / measure 锁内复核）

**新模块 `app/hal/base_station_compatibility.py`**：

```
BaseStationExecutionRequirements(frozen dataclass)
  schema_version: 1
  requested_rat: "nr5g" | "lte"
  required_operations: tuple[str, ...]   # 上表 5 个，构造器给定
  mac_profile: None                       # 显式 absent 槽位；P2-54 扩展本 schema，
                                          # 本片绝不发明判据（条目红线）
  digest                                  # canonical JSON sha256

evaluate_base_station_compatibility(requirements, manifest) -> verdict
  纯函数、零 I/O、零 DB。检查：
  ① requested_rat ∈ manifest 派生 rats（源自 rat_capabilities）
  ② required_operations ⊆ manifest.operations
  输出 CompatibilityVerdict(frozen)：
  compatible: bool；reasons: tuple[str,...]（不兼容时逐条）；
  requirements_digest / manifest_digest（对账后复核用）
```

**站点 A（freeze，拒入口）**：`freeze_base_station_adapter_profile` 内、resolve 之后：
- 从 execution 绑定的 TestCase 读 `radio_technology` 构造 requirements；
- `resolved.manifest` 存在（configured / not_applicable 两态）→ evaluate，不兼容 raise
  `ValueError`（runner 已有捕获链 → `CaseNotExecutable`）；
- `diagnostic_unbound`（无 manifest）→ verdict 记 `no_adapter`，不拦（见域枚举表）；
- verdict + requirements（含 digest）写进 frozen dict，随既有 `digest` 一并封存。

**站点 B（measure 锁内复核，防漂移）**：`measure.py` 现有 live 复核处：
- 从 frozen dict 取 requirements，对**当前** live manifest 重新 evaluate；
- verdict 与冻结时不一致、或 requirements/manifest digest 漂移 → 拒绝进入首次 I/O。

**判据红线**（条目原文，测试要钉死）：不读 TestCase 名称、不读 adapter 名称前缀、
不读 Mock 自报能力并集（`get_supported_technologies`）。

### 已拒绝的替代

- **只修 MockBS 双 RAT 并集**：只遮本次复现，保护不了未来 adapter / operation 维度；
  且那是 P2-64 的地盘（roadmap 已批准的分片边界）。
- **门放在 measure executor 内**：太晚 —— execution 已建行、报告链已启动；
  且 commissioning 入口不经过 measure。freeze 是两入口的汇聚点。
- **复用 `resolve_base_station_execution_plan` 扩维度**：那是"adapter 有没有能力做 X"
  的能力计划，不是"TestCase 要什么 vs adapter 给什么"的对账；混进去会把两种语义
  搅在一张表里（P2-50 设计边界）。

## 5. 明确不做（⑦ 边界）

1. **不改 MockBS**（能力并集、`"CMW" in model` 嗅探）→ P2-64。
2. **不动 Readiness / preview / GUI** → P2-65（它将复用本片同一 evaluator 与 digest）。
3. **不动证据终态语义 / 历史回填** → P2-66。
4. **不发明 MAC profile 判据** → 槽位显式 `None`，P2-54 扩展同一 schema。
5. **零新 SCPI、零仪器语义断言**。
6. **不动真实驱动的后置 RAT 拒绝**（`apply_requested_config`）——它是纵深防线，留着。

## 6. 验收（条目原文四拒两放 + 判据红线）

拒绝（发生在零 connect / 零 SCPI / 零 phase progress / 零报告之前）：
① UXM manifest + requested lte；② CMW manifest + requested nr5g；
③ manifest 不含所需 operation（fake manifest 缺 `measurement_window`）；
④ 冻结后 manifest/binding 漂移（站点 B）。
放行：⑤ UXM + nr5g；⑥ CMW500 + lte。
另：⑦ `diagnostic_unbound` 保持既有语义（verdict=`no_adapter`，可诊断运行）；
⑧ 判据红线测试：把 TestCase 名字改成 "CMW500 xxx" / driver 自报双 RAT，都**不影响** verdict。

## 7. 动手前四行

- **搜索命中**：memory 三条 + 条目红线（不读名称/并集）+ P2-50 设计边界（能力计划 ≠ 需求对账）；
  freeze 函数 docstring "Pure lock-time check; never opens a session" —— 本片 evaluate 同样纯函数，不破坏。
- **必要性**：逻辑上不可能的 TestCase × Adapter 组合能完成执行并出报告（execution 7ae66c69 实证）。
- **范围**：新模块 1 + freeze 侧 1 + measure 复核侧 1 + runner 错误链核对 + 测试；
  Mock/Readiness/证据/日志四个派生面**不动**（P2-64~67 已排队）。
- **爆炸半径**：原 bug 最坏 = 不可能组合静默出报告；修完最坏 = 兼容组合被误拒（fail-closed 方向，
  且有 ⑤⑥ 放行用例钉住）。**Y ≤ X**。
