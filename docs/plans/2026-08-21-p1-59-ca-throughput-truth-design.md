# P1-59 CA 多小区吞吐真值设计

## 可观察故障

正式 NR-CA 用例会按 `component_carriers[1:]` 添加并激活 SCell，但当前 UXM KPI
读取始终查询 `...OTA:{cell}?`，只得到 PCell；统计窗口前的
`BTHRoughput:CLEar` 却清空全部 NR 小区。PCell-only 数值随后被
`MeasureExecutor` 聚合，进入 `throughput_pass` 和正式报告，形成看似可信但系统性偏低的
CA KPI。

同一入口还存在四种静默降级：`uxm_config_mode=inherit` 跳过 SCell、驱动缺少 SCell
能力、任一 `add_secondary_cell()` 返回 `False`、`activate_secondary_cells()` 返回
`False`。当前实现都会继续正式测量，并把 PCell 结果放进 CA 报告。

## 厂商真值

本片只使用仓库本地 Keysight UXM SCPI Reference 已明确给出的命令，不推断别的方言：

- `UXM5G_SCPI_02_NR_PHY_Measurements.md`，`NR BLER/Tput > DL OTA > DL OTA all NR Results`：
  `BSE:MEASure:NR5G:BTHRoughput:DL:THRoughput:OTA:ALL?`，返回 6 个 Double，注释明确
  为所有 NR cells 结果之和；
- 同文档 `NR BLER/Tput > UL OTA > UL OTA all NR Results`：
  `BSE:MEASure:NR5G:BTHRoughput:UL:THRoughput:OTA:ALL?`，同样返回所有 NR cells
  结果之和；
- 两条命令的 Application Mode 均为 `NSA | SA`，单位和六元素下标沿用相邻的
  OTA throughput 契约：`current=idx1`、`average=idx4`、bps。

命令只填入已有手册证据且现场使用的 `UxmLteNrIratProfile`。其他 profile 继续
`None` 并 fail-closed，不按相似路径猜命令。

## 产生方与消费方全集

| 层 | 当前站点 | 本片裁决 |
|---|---|---|
| 配置真值 | `MIMOOTAConfiguration.component_carriers` | `[0]` 为 PCell；长度大于 1 才要求 `nr_all_cells` |
| SCell 写入口 | `MeasureExecutor` 的 inherit / driver capability / add / activate 四路 | 任一路不能确认全部 SCell 激活即在任何吞吐采样前 FAILED |
| KPI 命令表 | `UxmTestApp` / `UxmLteNrIratProfile` | 新增 DL/UL `*_OTA_ALL` 可空字段；只在有出处的 IRAT profile 填值 |
| KPI 读取 | `RealUxmDriver.get_throughput_metrics()` | 显式接收 scope；`pcell` 用 `{cell}?`，`nr_all_cells` 只能用 `ALL?`，缺命令不得回退 |
| 统计窗口 | UXM / BaseStation / Mock / CMW500 `measure_throughput_window()` | scope 作为关键字参数贯穿；不支持 CA 的驱动在上游已 fail-loud |
| KPI 数据契约 | `ThroughputMetrics` / `to_dict()` / measurement log | 同行携带 `throughput_scope`，旧对象或未知 scope 不得被正式链猜成 CA |
| 正式聚合 | `MeasureExecutor._trusted_throughput_value()` | 除 `kpi_valid=True` 和有限数值外，还必须精确匹配本次要求的 scope |
| 方位/相位载荷 | `azimuth_results` / measure result | 每个方位和顶层写 scope；`throughput_verified` 只有全方位同 scope 才为真 |
| Analysis | `AnalysisExecutor` | 继续只消费显式 `throughput_verified=True`；否则 UNKNOWN/N/A |
| 报告构建 | `_build_mimo_ota_content_data()` | 重新核对载波数、顶层 scope、逐方位 scope；不匹配则隐藏 KPI |
| 历史报告 | `report_has_provenance_trust()` | throughput trust schema 从 1 升 2；旧 schema 1 包括既有 PCell-only CA 报告均 fail-closed，必须安全重建 |
| 诊断/证据 | compatibility critical set、P0-5 evidence catalog | 把聚合命令纳入当前 profile 能力普查；证据目录说明 per-cell/ALL 两种合法 query |
| 非正式监控 | `RealUxmDriver.get_metrics()` | 默认仍读 PCell，不伪装为正式 CA 聚合；不改变 Dashboard 实时语义 |
| CMW500 | `RealCmw500Driver` | 仍因缺厂商返回契约保持吞吐无效；不借本片猜 CA 命令 |
| Mock | `MockBaseStation` | 可接受 scope 以保持接口对称，但模拟值仍由既有 provenance 门排除 |

## 设计

### 1. scope 是数据契约，不是日志提示

`ThroughputMetrics` 新增白名单字符串 `throughput_scope`：

- `pcell`：单载波 per-cell query；
- `nr_all_cells`：经 `OTA:ALL?` 取得所有 NR cells 之和；
- `unknown`：旧对象、缺命令或无法证明；
- `simulated`：mock 诊断值。

正式调用方传入期望 scope，并要求返回 scope 精确相等。不能从“配置里有几个 CC”事后猜
某个已经产生的数值是什么口径。

### 2. CA 配置是全有或全无

当 TestCase 声明 SCell 时：

1. `inherit` 模式拒绝正式 CA，因为它没有本次 SCell 写入/激活真值；
2. 驱动必须同时具备 add 与 activate；
3. 每个 SCell 都必须添加成功；
4. 全部添加后，activate 必须显式返回 `True`；
5. 只有满足以上条件，测量 scope 才设为 `nr_all_cells`。

任一步失败都在 signaling/正式 KPI 采样前返回可操作错误。不得继续少载波运行，也不得把
PCell-only 结果加标签后放行。

### 3. scope 决定命令，缺命令不降级

单载波保持现有 per-cell DL/UL、BLER、CQI、RI 路径。CA 只把 DL/UL throughput
查询换成 `*_OTA_ALL`；BLER/CQI/RI 仍是既有 PCell/UE 口径，本片不扩写无出处的聚合语义。

请求 `nr_all_cells` 时，DL 或 UL 聚合命令缺失/失败分别保持该 KPI 的 `None` 与
`kpi_valid=False`，并在日志记录 scope；绝不回退 per-cell。

### 4. 报告 trust schema 升级

新报告只在以下条件全部成立时写 `throughput_trust_schema_version=2` 且
`formal_throughput_verified=true`：

- measure 顶层 scope 与 `carrier_aggregation.num_component_carriers` 推导的期望一致；
- 每个方位 `throughput_valid is True`；
- 每个方位 scope 与顶层期望一致；
- 既有真实仪器、路径损耗等门继续成立。

schema 1 不包含口径证明，不能区分单载波真值与 CA PCell-only 历史数值，因此读取、详情、
下载和重生成信任门一律不再接受 schema 1。P2-26 的安全重建链会用当前执行证据生成 schema 2；
缺少 scope 的历史执行保持 UNKNOWN/N/A。

## 错误与安全方向

- 误拒绝 CA：操作员看到明确失败，可修配置或驱动能力；代价是本次不出报告。
- 误放行 CA：少载波或 PCell-only 数值进入正式报告，可能被签字；代价远高于误拒绝。

因此所有未知、旧记录、缺命令、部分添加和未确认激活均选择 fail-closed。

## 实现期内审补充：SCell 写入不能只信布尔值

第一次实现虽然让上游消费了 `add_secondary_cell()` / `activate_secondary_cells()` 的
布尔返回，但真实 UXM 驱动仍有两条假成功路径：空 SCell 清单返回 `True`，以及写完只等
`*OPC?` 而不读取错误队列。实现期 fresh review 已按 TDD 收口：

- add 前验证当前 profile 的完整命令模板，缺任一项零 I/O 失败；
- add 前清历史错误、写后消费错误队列，任何拒绝或错误门不可用均失败；
- 配置清单与错误队列只能证明命令被接受，不能证明 UE 实际激活全部 SCell；
- 当前手册没有逐 SCell active-state 权威回读，因此真实 UXM 在发送激活动作前即
  fail-closed，不能以 `*OPC?`、清单或干净错误队列替代动作真值；
- 只有未来补齐带厂商出处、能精确确认预期 SCell 集合的回读后，正式 CA 才可放行。

当前 `UxmLteNrIratProfile` 有来源的命令面只足以查询聚合吞吐，不足以完成本片要求的
逐 SCell 配置/激活真值；`Uxm5GProfile` 同样没有逐 SCell 激活态权威回读。因此真实 UXM
CA 在补齐厂商出处与现场兼容性证据前统一明确失败。此处选择“无报告”而非“PCell-only
假报告”，现场半保持 Hardware Blocked。

## 验收

1. 单载波仍发送 per-cell DL/UL query，scope=`pcell`；
2. CA 发送 DL/UL `OTA:ALL?`，不发送 per-cell throughput query；
3. 聚合命令缺失时不回退，吞吐值为空且 validity=false；
4. inherit、缺能力、任一 add 失败、activate 失败均在采样前 FAILED；
5. scope 不匹配的有效数值不能进入方位均值、Analysis 或报告；
6. 新报告 trust schema=2，旧 schema=1 不再被视为可信；
7. compatibility、相关回归、完整 rule gates、compileall、diff-check 全绿。

## 开发完成验证（2026-08-21）

以下结果运行于代码提交 `93acacc` 的精确产品/测试内容；其后只追加本验证记录：

```text
cd api-service
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q \
  tests/test_p1_59_ca_throughput_truth.py \
  tests/test_uxm_kpi_readback.py \
  tests/test_p1_54_kpi_valid_contract.py \
  tests/test_mimo_ota_report_verified_backcompat.py \
  tests/test_uxm_scpi_compatibility.py \
  tests/test_p1_47b_instrument_evidence.py \
  tests/test_measure_input_and_param_branches.py \
  tests/test_mimo_ota_precheck_cal_gate.py \
  tests/test_rule_gates.py
结尾：279 passed, 649 warnings in 5.38s

/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m compileall -q app tests
git -C .. diff --check
/Users/simon/Tools/MIMO-First/api-service/.venv/bin/python -m pytest -q -o log_cli=false
结尾：4166 passed, 5 skipped, 4285 warnings in 89.49s
```

R1 P1 的 TDD 证据：同一条定点测试修前为 `1 failed`（实际返回 `True`），修后为
`1 passed` 且断言 query/write/error-drain 均未发生。fresh 尾审 P1/P2/P3=0。

## R2 P1 尾修验证（2026-08-21）

R2 指出报告虽然已按 scope 保持 UNKNOWN，但 Analysis 和执行历史仍只消费旧
`throughput_verified` / `validation_pass`，可把同一份旧 CA PCell-only 证据重新发布为
PASS/FAIL。修复将载波数、measure 顶层 scope、逐方位 validity/scope 收敛到共享判据，
正式报告、Analysis 与历史列表三条消费路径全部复用；非 MIMO 历史语义不变。以下结果
运行于代码/测试提交 `b057c4c` 的精确内容；其后只追加本验证记录。

TDD RED：两条定点用例修前均失败，分别观察到 Analysis=`PASS`、历史=`true`；GREEN 后
均保持 UNKNOWN/`null`。当前 HEAD 的验证结果：

```text
相关链 + 完整 rule gates：296 passed, 670 warnings in 5.28s
全后端：4168 passed, 5 skipped, 4285 warnings in 91.72s
compileall：通过
diff-check：通过
fresh 尾审：P1/P2/P3=0
```

## 非目标

- 不改变 BLER/CQI/RI 的聚合口径；
- 不为 5G_NR_Test 或 CMW500 猜测未确认命令；
- 不把 mock 数值放入正式 KPI；
- 不现场验证 UXM firmware 支持性；该证据仍由 compatibility 序列取得。

## R3 P1 尾修验证（2026-08-21）

R3 指出部分 SCell 已添加、后续添加或激活失败时，`MeasureExecutor` 会在 `try` 内直接
返回；`finally` 虽然执行清理，但失败结果已构造完成，清理 warnings 被丢弃。同时
`cleanup_chamber_instruments()` 没有消费 `remove_all_secondary_cells()` 的布尔契约，
真实驱动返回 `False` 时仍表现为清理成功，残留 SCell 可污染下一次单载波执行。

代码/测试提交 `9ad5969` 按 fail-closed 收口：清理必须精确返回 `True` 才算确认；CA
配置 blocker 先穿过 cleanup，再构造失败结果，未确认移除会同时进入 `error_message`、
`warnings` 与 `measurements.cleanup_warnings`。TDD RED 两条修前均失败：一条观察到空
warnings，另一条只收到原始 `SCell 2 添加失败`；GREEN 后均通过。

```text
定点 RED → GREEN：2 failed → 2 passed
相关及安全对称链：348 passed, 676 warnings in 5.39s
全后端：4170 passed, 5 skipped, 4290 warnings in 92.76s
compileall：通过
diff-check：通过
fresh 尾审：P1/P2/P3=0
```
