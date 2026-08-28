# NEW-1 F64 活动输出集合设计

## 可观察故障

`propsim_f64_output_level_windows` 在驱动没有活动输出缓存时，把
`SYSTem:INFO?` 的整机衰落通道数当作物理输出口数。现场加载 16 口场景时，序列因此
查询了 32 口；前 16 口合法，另 16 个未配置口无回复，最终把本来可通过的活动口检查
判成 `UNDETERMINED`。

## 全集与权威来源

- 端口集合产生方：诊断参数 `outputs`、驱动 `_active_output_ports` 缓存、
  `SYSTem:INFO?` 通道数兜底。
- 端口集合消费方：逐口 `OUTPut:LEVel:AMPlitude:LIMits?` / `CH?` 查询、结果
  `extra.ports`、`unknown_ports`、摘要与最终 verdict。
- 当前仿真物理输出口真值：按 PROPSIM ATE 官方拓扑遍历序列读取
  `DIAGnostic:SIMUlation:MODel:INFO?`、`GROup:GET?` 和每组
  `GROup:OUTputs:GET? <group>`，以组输出并集作为活动物理输出口集合，并用
  `MODEL:INFO?` 的输出数量交叉核对。
- 手册未规定对未配置输出口查询电平窗口时的回复形态，不能用空回复、异常或超时反推
  “未配置”。

手册依据：Propsim ATE environment and practices AN §3.2（印刷页 72–73）；Propsim
User Reference Rev 10.2 §20.4.3.6、§20.4.7.1、§20.4.7.3（印刷页 234、289）。

## 方案

序列每次运行都直接读取当前仪表拓扑，不复用可能为空或过期的驱动缓存，也不新增驱动
命令。只有实时拓扑完整、正整数、组数有界、组输出并集非空且集合大小与
`MODEL:INFO?` 输出数量一致时，才进入逐口电平查询。

删除 `outputs` 人工覆盖参数和 `SYSTem:INFO?` 通道数兜底。这样操作员不能通过缩小口集
绕过真实活动口，缓存为空时也不会把硬件容量冒充当前场景拓扑。拓扑读不到或两个来源
矛盾时，不发任何逐口查询，结果保持 `UNDETERMINED`。

`extra.port_source` 固定标记为 `live_group_output_union`，并保存实时活动口列表。未进入
活动集合的硬件口不查询、不阻塞；由于手册没有提供整机物理输出口编号全集，本序列不
编造“未配置口号”列表，只在摘要中明确其他口未探测。

## 状态空间

- 身份不符或旧 `outputs` 参数非空：`ABORTED`，逐口查询不发。
- 仿真未打开、拓扑缺失/畸形/矛盾：`UNDETERMINED`，逐口查询不发。
- 活动口任一值读不到：`UNDETERMINED`。
- 活动口任一当前值越窗：`BLOCKER`。
- 全部活动口在窗内且错误队列零残留：`SUCCESS`。

## 范围

只修改该诊断序列、专项测试和当前 roadmap 状态；不修改正式 MIMO OTA 执行、不引入新
SCPI、不把本地测试冒充现场复验。合并后 NEW-1 仍保留“现场重跑并取得 SUCCESS”这一半。
