# P0-9B-1 CMW500 PCCBBBoard 权威回读设计

## 可观察故障

CMW500 已接受 LTE `1CC - nx2` 七字段 Route，通用
`ROUTe:LTE:SIGN<i>?` 也能回读场景和六个物理路径字段，但该查询的第二字段是保留的
`Controller`，不是 `PCCBBBoard`。因此当前实现必须保持 `route.confirmed=false`，正式 KPI
无法开放。

## 厂商依据

- R&S *Remote Control via SCPI - Getting Started* 1179.4592.02-04，§3.6，印刷页 22：除非
  特别声明，否则每个 setting command 都定义对应 query；query 由在 command header 后追加
  `?` 形成。
- R&S *CMW LTE UE User Manual* 1173.9628.02-41，§2.6.8.1，印刷页 630–631：
  `ROUTe:LTE:SIGN<i>:SCENario:TRO:FLEXible` 设置 `PCCBBBoard` 和六个 RX/TX 路径字段，
  未声明 setting-only。
- 同一 LTE 手册 §2.6.1.4，印刷页 362–365：查询返回物理 connector 名称；Base Band Unit
  与 RX/TX module 的合法枚举也在该节定义。

因此对应的有据查询为：

```text
ROUTe:LTE:SIGN<i>:SCENario:TRO:FLEXible?
```

## 最小实现

1. 在现有 CMW500 command catalog 中登记上述 query，并紧邻记录两份手册出处。
2. 增加严格七字段 parser：字段数必须精确为 7，每个值必须是手册允许形态的裸字母数字 token；
   不接受空值、`NAV`、分隔符或 requested 回填。
3. Route 写入、错误队列为零后，先执行 TRO-specific query 取得七字段，再保留现有通用
   `ROUTe:LTE:SIGN<i>?` 核对活动场景与六个物理路径。
4. 只有两份回读互相一致且完整匹配 execution-frozen requested Route 时，才写入完整
   `applied` 并令 `confirmed=true`。任一查询不支持、超时、字段不一致或错误队列非零时继续
   fail-closed。

## 范围边界

- 不新增外部 RF router、功率预算、路径补偿或 GUI 字段。
- 不把写入成功、`*OPC?`、空错误队列或保留 `Controller` 字段当作 PCCBBBoard 证明。
- 不用真机未验证结果关闭现场项；本地实现完成后 P0-9B-1 仍标记“待现场复验”。

## 验证

- command builder/parser 定点 RED→GREEN；
- Route 驱动测试覆盖完整确认、PCC mismatch、物理路径交叉回读 mismatch、query 异常；
- CMW500 measurement/evidence 相关链与规则门回归；
- 现场使用同一诊断/正式 TestCase 验证真机是否接受该只读 query，失败时保留诊断能力且正式
  KPI 继续 UNKNOWN/N/A。
