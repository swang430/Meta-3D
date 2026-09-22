# P1-80 F64 许可查询错误归属设计

## 可观察故障

2026-09-16 同一 F8800A 连续两次运行 `propsim_f64_license_truth`：

- `SYSTem:CALIBration:VALid?` 返回空串，同时错误队列出现
  `-200,"Execution error;No simulation opened"`；
- `SYSTem:CALIBration:USER:GET?` 返回空串，同时错误队列出现
  `-100,"Command error;ATE command not supported"`；
- 旧实现只在全部业务查询结束后排一次错误队列，因而两条空回复先被显示为绿色，错误只能作为
  无归属的收尾残留出现。

这会把“许可列表已读到”错误扩张成“校准和用户对齐也可信”。本片只修诊断证据归属，不关闭
仍需同一真机复验的 P1-2。

## 全集与边界

序列的查询集合保持不变；不新增、不猜测 SCPI。受影响的查询分为四组：

1. 身份与许可：`*IDN?`、`SYSTem:INFO?`；
2. 校准：`CALIBration:LIST?/VALid?/GET?`；
3. 用户对齐：`CALIBration:USER:GET?/INFO?`；
4. 仿真状态与干扰源：`DIAG:SIMU:STATE?`、按既有前置条件发出的
   `OUTPut:INTERFerence:GET?`。

`SYSTem:ERRor?` 仍是 Propsim User Reference Rev 10.2 §20.4.2.1 已有的只读错误队列接口。
本片不使用 `*CLS`，不临时打开仿真，也不把当前固件观察推广成所有 F64 的能力结论。

## 方案

1. 取得诊断独占租约后，先排空并归档开场 residue。开场排水不可判时立即 `ABORTED`，不发业务查询。
2. 该序列的仪表租约关闭 1 Hz 实时监控以阻止新轮次，并让整个序列（开场排水、全部业务查询、
   逐查询排水、收尾排水）持有 F64 现有可重入 SCPI 锁；即使旧监控轮已启动，也须先退出单命令锁，
   此后不能再插入序列事务。非零错误归属到刚执行的查询；排水异常、非法回复或达到上限均使该查询失败。
3. 回复、归属错误与命令值域共同决定步骤是否成立。空串只有在错误队列干净且该命令手册允许时
   才能成立；例如 `USER:GET?` 的干净空串表示未启用，而 `VALid?` 空串始终非法。
4. 分别输出 `license`、`calibration`、`user_alignment` 的 `CONFIRMED / UNKNOWN`。
   `CONFIRMED` 只表示回复可归属并可解析，不表示校准有效或用户对齐已启用。
5. 保留顶层 `SUCCESS / BLOCKER / UNDETERMINED / ABORTED` 与既有开放 `extra` 载荷，避免制造第二套
   API/GUI 真值。任一业务查询失败或子域未知为 `BLOCKER`；仅收尾出现无法归属的异步残留时为
   `UNDETERMINED`。

## 验收

- 精确复现两条现场反例并证明不再显示绿色；
- 证明干净的 `USER:GET?` 空串仍能确认“未启用”；
- 证明开场历史 residue 被归档但不污染本次查询；
- 证明查询后错误队列不可判、非法 `VALid?`、错误 payload 与身份不符均 fail-closed；
- 证明 `VALid?` 只接受恰好两个 0/1，尾随字段不能被截断后确认；
- 证明该序列在禁用监控的租约与同一 F64 SCPI 事务锁中运行，其他诊断的监控默认值不变；
- 相关诊断、规则门和全后端回归通过；
- 同一 F8800A 的复验仍是 P1-2 的独立现场关闭条件。
