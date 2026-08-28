# P2-9 EMCenter ERROR 3 精确分类设计

## 背景与可观察故障

CAICT-Lab-1 的 ETS-Lindgren EMCenter 系统软件版本为 `2.5.1`。2026-08-27 现场运行
`emcenter_switch_health` 时，`INTLK? SAFETYRELAY` 精确返回：

```text
ERROR 3;(INTLK? SAFETYRELAY);
```

机箱身份、槽位身份和已配置继电器回读均正常，但诊断序列把所有非 `0` / `1` 回复都判为
`BLOCKER`，因此健康的已知现场组合无法得到 `SUCCESS`。上面的完整字面量来自
2026-08-27 操作员粘贴的诊断结果，并在本文首次固化；当日现场摘要
`docs/site-debug/2026-08-27-lte-cmw500-onsite-summary.md` 只保留了缩写 `ERROR 3`。
厂商手册只定义了 `0` / `1` 值域，并没有为该旧固件的错误回复给出通用语义。

## 方案选择

采用诊断序列内的精确白名单，不修改通用错误解析器，也不复用驱动现有的宽松
“只要不等于 `1` 就放行”行为。只有以下三项同时精确匹配时，才归类为
`known_unsupported`：

1. `VERSION_SW?` 去除首尾空白后的回复为 `2.5.1`；
2. 查询命令是序列既有的 `INTLK? SAFETYRELAY`；
3. 原始回复去除首尾空白后精确等于 `ERROR 3;(INTLK? SAFETYRELAY);`。

这是一条现场观察白名单，不推广为“ERROR 3 的通用含义”，也不声称安全互锁为 0。

## 数据流与判定

序列继续按既有顺序读取 `*IDN?`、`VERSION_SW?`、槽位身份、继电器位和互锁。互锁步骤
增加一个显式分类字段：

- `inactive`：回复为 `0`，互锁已确认未激活；
- `active`：回复为 `1`，继续判为 `BLOCKER`；
- `known_unsupported`：只命中上述精确三元组，步骤成功但只表示“该查询在此现场组合中
  已确认不支持”；
- `invalid`：其他非空、非 `0/1` 回复，继续判为 `BLOCKER`；
- `no_response`：无回复或超时，沿用现有 `BLOCKER`。

`extra["interlock"]` 继续保留原始回复以兼容现有消费者，并新增
`extra["interlock_classification"]`。成功摘要根据分类分别表述：`inactive` 才能写
“互锁 0”；`known_unsupported` 必须写“互锁查询已确认不支持”，不能把未知安全状态伪装成
未激活。

若槽位配置缺失或继电器类型未知，仍按现有规则得到 `UNDETERMINED`；精确白名单不覆盖这些
独立缺口。若其余步骤存在 blocker，整体仍为 `BLOCKER`。

## 错误处理与安全边界

- 不新增、替换或重排任何 SCPI 命令。
- 不把字符串包含、前缀匹配或正则用于放行。
- 其他固件返回同一字面值仍 `BLOCKER`。
- 固件 2.5.1 返回缩写 `ERROR 3`、其他命令回显或其他错误仍 `BLOCKER`。
- 原始回复继续进入 `SequenceStepResult.raw` 和 `extra["interlock"]`。
- 不修改 `EtslSwitchDriver.connect()`；它的宽松连接兼容属于独立待评估问题，避免本片扩大到
  驱动生命周期和安全策略。
- TopologyEditor mapping 与真机继电器切换仍属于 P2-9 的后续现场工作，不在本片实现。

## TDD 与验收

先写行为测试并观察 RED：

1. 精确 2.5.1 + 完整现场回复，在其他回读健康时得到 `SUCCESS`、
   `known_unsupported`，且摘要不包含“互锁 0”；
2. 其他固件的相同回复继续 `BLOCKER`；
3. 2.5.1 下的缩写 `ERROR 3` 继续 `BLOCKER`；
4. 2.5.1 下的其他错误或不同命令回显继续 `BLOCKER`；
5. 既有 `0` / `1`、超时、值域和只读不变量测试保持通过。

GREEN 后运行 EMCenter 序列与驱动协议相关测试、规则门、全后端、`compileall`、单一
Alembic head 和 diff-check。fresh 内审 P1 为 0 后开 Ready PR，按 R1→R2 流程收口。
本地测试只证明分类逻辑；现场仍需重跑 `emcenter_switch_health` 并取得 SUCCESS 才能关闭
P2-9 现场半。
