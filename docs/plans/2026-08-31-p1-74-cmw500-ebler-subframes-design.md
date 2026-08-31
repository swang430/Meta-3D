# P1-74 — CMW500 Extended BLER 统计基真值闭环（非现场半）设计稿

**日期**：2026-08-31
**状态**：设计稿，供 review
**Roadmap**：P1-74（已批准队列首位）

## 1. 可观察故障（本片唯一要修的那一个）

TestCase 的 `stat_count`（统计子帧数）**从未到达仪器**。真值链在
[`measure.py:2882`](../../api-service/app/services/mimo_ota/executors/measure.py) 断掉：

```python
window_s = max(config.stat_count / 1000.0, _MOCK_WINDOW_FLOOR_S)
```

TestCase 说「统计 5000 子帧」→ 系统只把它换算成「睡 5 秒」→ 仪器的
`CONFigure:LTE:SIGN<i>:EBLer:SFRames` **全仓零下发**（`grep -rn SFRames --include='*.py'`
今天只命中 3 行注释），于是仪器沿用它自己保留的值：`*RST` 是 10E+3，而上一
session 可能把它设成任意值。

**「睡够时间」不等于「统计够子帧」。** 手册 p.938/p.953 明确：无 stop condition
（正式窗口正是 `SCONdition NONE`）时 SFRames = 每 measurement cycle 处理的子帧数，
cycle 的数量与边界由仪器决定，不由主机 sleep 决定。

后果：两次业务参数完全相同的正式执行，统计基可以不同 → 吞吐/BLER 的置信区间
不同 → **正式 KPI 不可重复**，而报告里看不出差别。

## 2. 手册取证（CMW500 无 NotebookLM，本地手册为权威源）

底本：`Instrument_API_Doc/R&S CMW500/CMW_LTE_UE_UserManual_V4-0-250_en_41 (2).pdf`
（User Manual 1173.9628.02 ─ 41）。每条带印刷页码。

| 项 | 手册原文结论 | 印刷页码 |
|---|---|---|
| 命令形式 | `CONFigure:LTE:SIGN<i>:EBLer:SFRames <Subframes>` | p.953 |
| 主语义 | "the number of subframes (= number of transport blocks) to be processed **per measurement cycle**" | p.953 |
| GUI 侧同义 | "**For measurements without stop condition**, this parameter defines the number of subframes to be processed per measurement cycle (a single-shot measurement covers one measurement cycle)" | p.938 |
| confidence 例外 | "**For confidence BLER measurements**, this parameter specifies only the length of the throughput result trace. It does not influence the duration" | p.938 / p.953 |
| 参数域 | integer，Range `100 to 400E+3` | p.953 |
| 复位值 | `*RST: 10E+3` | p.953 |
| 最低固件 | V3.0.30 | p.953 |
| 选件 | 定义块**无** Options 行 → 无选件要求 | p.953 |
| 回读合法性 | 命令块未标 `Query only` / `Event`；手册 "Command usage" 通则：「If the usage is not explicitly stated, the command allows you to **set parameters and query parameters**」 | §1.2.4 p.15 + Command usage 节 |
| FDD 计数口径 | 所有已调度与未调度的下行子帧都计入 | p.938 |
| TDD 计数口径 | 下行、上行、特殊子帧都计入 | p.938 |
| 并行流 | 经多个下行流并行发送的一个已调度下行子帧**计为 1 个** | p.938 |

§3.3.1（p.940）编程示例把 SFRames 直接放在 continuous 配置里，与本片下发位置一致：

```
CONFigure:LTE:SIGN:EBLer:SCONdition NONE
CONFigure:LTE:SIGN:EBLer:REPetition CONT
CONFigure:LTE:SIGN:EBLer:SFRames 1000
CONFigure:LTE:SIGN:EBLer:ERCalc ERC1
```

### 2.0 NotebookLM 二次确认（2026-08-31 补做的实证前置）

**本片一度漏做这道前置。** 初判「CMW500 无 NotebookLM notebook」，凭的是「我没见过」，
而实际存在 notebook **R&S CMW500**（`256076ee-5bd9-4f45-85f6-d7318e7556d0`，6 source）。
用户指出后补查。CLAUDE.md 的规矩是：只要碰 HAL 驱动或结论依赖仪器语义就必须在
notebook 里拿确认 —— 把「我没查到」当成「不存在」正是该规矩要防的形态。

补查结果：§2 表格的每一条**均获逐字确认**，另补出四条本地遗漏的手册事实：

| # | 手册原文 | 出处 | 对本片的影响 |
|---|---|---|---|
| 1 | `"None"  The measurement is performed according to its "Repetition" mode and the specified "No. of Subframes". No confidence BLER result is determined.` | p.937 | 比 p.938 更直接地证明 continuous 下 SFRames 生效 |
| 2 | `To avoid misleading results, a running measurement is re-started if a parameter with direct impact on the results is changed. All values acquired so far are discarded; the statistics counters are re-set to zero.` | Base Software UM 1173.9463.02-06, printed p.139 | **SFRames 必须在 INIT 之前下发**。本片放在 window configuration 组正是此位置 —— 原本是碰巧正确，现在有依据 |
| 3 | REPetition 远程复位默认值为 `SINGleshot`；单次模式下跑完一个 SFRames 即停进 RDY | p.953 | 解释既有代码为何必须显式下发 `CONTinuous`（本片不改动该行为） |
| 4 | TOUT 若在首个测量周期完成前到期，测量被强制终止进 RDY、可靠性指示器置 1、统计深度未达标 | p.952-953 | 解释既有 `TOUT 0` 的必要性（本片不改动） |

### 2.0.1 一条**明确不做**的诱人推论（边界，写死在这里）

`FETCh:LTE:SIGN<i>:EBLer:PCC:ABSolute?` 的字段手册逐字定义（**既有代码早已解析**）：

- 第 4 字段 `<4_Subframes>` = `Number of already processed subframes (per downlink stream)` → `subframe_count`
- 第 9 字段 `<9_Scheduled>` = `Number of already sent scheduled subframes (per downlink stream)` → `scheduled_count`

拿 `subframe_count` 与请求的 SFRames 比对，看起来是「真实生效端」的完美证据。**本片明令不做**：

- 手册**没有说明** continuous 模式下 `already processed` 是每 measurement cycle 重置还是跨 cycle 累计。
- NotebookLM 初答曾把「有效基数小于 SFRames」讲成结论，经追问「这句在手册原文里有没有依据」后
  **自行撤回**，承认那是它的归纳而非原话。手册**原文**只有两句互相独立的陈述：
  p.938 `For FDD, all scheduled and unscheduled downlink subframes are considered.`；
  p.927/960 `percentage relative to the number of sent scheduled subframes.`
  由这两句**推不出** `subframe_count` 与 SFRames 的确切数值关系。

因此：`subframe_count` / `scheduled_count` 可作 outcome 观测，**不得**据此断言、不得据此
fail-closed、不得当 confirmed 判据。本片的 confirmed 判据只有一条 —— **回读设置值一致**（E3 APPLIED）。
「continuous 下该计数的语义」登记 Discovered，留给现场真机回答。

### 2.0.2 一道**没有加**的假门

手册 p.947 可靠性码 `28 - "unexpected parameter change"` 看似能守「运行中改参数」，但同段原文写明
`This situation can only occur in remote singleshot mode.` —— 本片是 continuous，该码**永不出现**。
为它加检查会得到一道永不触发的门，故不加。

### 2.1 取证过程中纠正的一次判据失效（留档，防重犯）

初判用「命令块内无 `Setting only` 标记 → 有 query 形式」，随即发现
**全手册 `Setting only` 只出现 1 次**，就是通则说明那句话本身 —— 判据退化成恒真，
是典型假门。改用反向验证：`Query only` 出现 408 次证明标记体系在提取文本里正常保留，
且 "Command usage" 节列出的例外**只有** `Query only` 与 `Event` 两类。最终判据两向验证：
SFRames 块内无这两个标记（阴性），而判据能在真标注命令上命中（阳性）。

### 2.2 同时确认 P2-51 内审 F1 的纠正无误

P2-51 曾把「只影响 trace 长度」当成 SFRames 的通用语义。手册原文显示该句
**明确限定于 confidence 模式**，而正式窗口是 continuous。本片据此把统计基
当作真值下发，与 P2-51 留下的注释一致。

## 3. 范围（改什么 / 不改什么）

### 3.1 本片做（非现场半）

1. **command profile**：新增 `ebler_subframes` spec（template / source_reference /
   purpose / minimum_firmware=V3.0.30），配 setter builder、query builder 与 parser。
   参数域按手册 `100..400E+3` 校验，越界 fail-loud，**不 clamp**（clamp 会静默改成
   另一个统计基，正是本片要消灭的形态）。
2. **execution-frozen 请求**：`BaseStationMeasurementWindowRequest` 增加统计基槽位，
   由 TestCase `stat_count` 驱动，随 execution 冻结。
3. **窗口序列**：在既有 window configuration 组（`TOUT 0` → `REPetition CONT` →
   `SCONdition NONE`）内加入 SFRames 写入，随后**回读**确认。
4. **fail-closed**：写失败、回读失败、回读值 ≠ 请求值、错误队列非空、越界请求，
   一律使窗口 `confirmed=False` 并写明 reason。**不得**从请求值、默认值、旧缓存或
   Mock 回填 confirmed。
5. **证据**：requested / applied / confirmed 三态 + exchange ids 落进窗口 evidence。
   ⚠️ **2026-08-31 内审 F4 更正交付边界**：窗口证据项**本身不进落库载荷** —— `append_base_station_measurement_window` 只取各项 `exchange_ids` 做账本校验，item 自身被丢弃（既有架构，非本片引入；`cmw500.extended_bler.window` 同样被丢）。因此本片实际交付的持久化是：请求值随 `trust.request.statistical_basis_subframes` 落库，**applied 值换源随 `trust.reason` 落库**（零契约改动）。结构化窗口级证据的持久化通道属既有缺口，已登记 Discovered。
6. **消费者审计**：正式 KPI 路径要求统计基 confirmed；未确认时保持 UNKNOWN/N/A。
7. **严格 TDD**：先红后绿，每道门配让它红的变异并实跑。

### 3.2 本片不做（明确非目标）

- **不改 UXM 侧 `stat_count` 路径** —— UXM 有自己的下发实现，不是本片故障。
- **不改 `window_s` 的 sleep 语义**，也不删 `_MOCK_WINDOW_FLOOR_S`。sleep 时长与
  cycle 完成的关系若存在缺口，是**另一个**可观察故障，按 ⑦ 登记 Discovered，不顺手修。
- **不新增任何其他 SCPI**。ERCalc 等相邻命令即便手册有据也不在本片目的内。
- **不给正式 KPI 加现场认证闸**。内审 F1 实测该闸**从未存在**（`kpi_valid` 在 happy path 即为 True，全仓 `field_verified`/`bench_only` 零命中），此状态自 P1-73B/C 即如此。加闸 = 新增机制 + 推翻既有行为，属越界，已登记 Discovered 待用户裁决。
- **不在共同配置层加仪器参数域**。内审 F5 指出 `stat_count` 在 schema/GUI 无上下限，但它是 adapter-neutral 字段，写进 CMW 的域会让厂商约束泄漏到共同层；正解应由 adapter manifest 声明域（P1-75 的天然载体）。已登记 Discovered。
- **不做现场半**。真机复验（至少两个不同统计长度连续执行、证明不继承旧状态）是
  P1-74 的关闭条件，本地测试不能替代；现场半完成前 CMW Extended BLER 正式 KPI
  保持 UNKNOWN/N/A。

## 4. 方案比较

### 方案 A：统计基归窗口层，execution-frozen 下发 + 回读（采用）

统计基是测量窗口的属性，与 P2-51 已定的「统计基归 Measurement Window 所有，
不塞回 MAC 配置层」边界一致。请求随 execution 冻结，回读确认，fail-closed。

### 方案 B：塞进 `configure_mac_throughput_test`

拒绝。P2-51 已判定 SFRames 归窗口层；MAC 配置层下发会让统计基与业务配置绑死，
且违反该方法自己的 `MEAS_TPUT_STAT_COUNT` 注释（写明「不在 MAC 配置层越权下发」）。

### 方案 C：只下发不回读

拒绝。写成功 ≠ 生效（本仓不变量 3）。不回读就无法证明统计基是本次 TestCase 的值，
故障（不可重复）依然存在，只是从「没设过」变成「设了但不知道有没有生效」。

## 5. 不变量

1. 模拟、未知、部分确认的统计基不进入正式 KPI；不得由请求值、默认值或旧缓存回填。
2. 新增命令的参数域、单位、复位值、固件下限必须有手册出处；越界一律拒绝不 clamp。
3. 写操作必须消费错误队列/拒绝/超时/取消；`*OPC?` 或函数返回成功不单独证明生效。
4. 现场复验与本地实现分别记状态；本地测试永不替代真机认证。

## 6. 动手前四行

- **搜索命中**：memory（`feedback_effective_end_not_nominal` 验证打在真实生效端 /
  `feedback_value_form_space` 值的形态空间 / `feedback_enumerate_before_changing` 改前列全集）；
  CMW500 无 NotebookLM notebook，以本地手册为权威源；目标文件自身禁令
  （`MEAS_TPUT_STAT_COUNT` 注释写明不在 MAC 层下发）已 grep 并遵守。
- **必要性**：TestCase 的 `stat_count` 不到达仪器，统计基继承仪器旧状态，正式 KPI 不可重复。
- **范围**：动 command profile + 窗口请求 + CMW 驱动窗口序列 + 证据/消费者 + 测试；
  枚举出的相邻缺口（sleep 与 cycle 关系、UXM 侧路径）进 Discovered，不在本片做。
- **爆炸半径**：原 bug 最坏 = 正式 KPI 统计基静默错误且无人知；修完最坏 = 统计基
  无法确认时窗口 fail-closed、KPI 显式 UNKNOWN/N/A。**Y ≤ X**（从静默错误变成显式拒绝）。
