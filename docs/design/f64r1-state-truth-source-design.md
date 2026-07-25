# F64R-1 设计:`DIAG:SIMU:STATE?` 接入为运行状态唯一真值源

> 状态:**设计评审中**(评审通过后开发)。Roadmap: F64R-1(F64 驱动 review 母题①
> 「该问仪器的地方在猜」之"运行状态"维度;P0-3 已落地加载路,本项收剩余)。
> 手册依据全部经 NotebookLM「PROPSIM 资料」查证(User Reference §20.4.3 / §20.5.2 /
> §20.6.1 + ATE AN §2.4/§2.5),关键条目附章节号。

## 1. 治的病

驱动的"在不在跑"由本地布尔 `_emulation_running` + **猜 -200 错误文字**决定。
`DIAG:SIMU:STATE?` 是手册唯一的运行状态真值源(§20.4.3.14),P0-3 之前全驱动零调用;
P0-3 只把**加载路**接上(CLOSE 后确认卸载)。剩余四个坑:

| # | 坑 | 现状 | 后果 |
|---|---|---|---|
| ① | **GO 豁免信号选错**(#221 遗留,review 母题①点名) | GO 被拒 -200 时回查 `STATIC?==0` 判"已在跑" | STATIC? 只报**旁路档**不报运行态:`STATIC=0 且 STOPPED`(停着、非旁路)时 GO 被拒会被误豁免成"已在播放" → 测量在**没有衰落播放**的状态下跑假数据 |
| ② | **GOS 豁免盲信错误文字** | GOS 被拒 -200 "Wrong device state" 一律当"本来就没在跑" | 同签名可能有别的成因;真没停住时 attach 直通预备假成功 |
| ③ | **监控面谎报** | `get_metrics` / `get_channel_state` 的 `emulation_running` 读内存缓存 | 后端重启后缓存 False 而硬件在播(2026-07-21 实证的形态)→ 仪表盘谎报"没在跑";反向漂移同理 |
| ④ | **旁路进出 running 漂移** | `set_passthrough_mode` / `clear_passthrough_mode` 各自内联猜 running | 手册确认"进旁路会**暂停**仿真、退旁路若之前在跑会**恢复**"(§20.4.6.25 + ATE AN §2.4.5),内联猜必然漂 |
| ⑤ | **超时挂死不自动恢复**(P0-1 遗留业务挂死盲区) | `_drain_after_timeout` 排水失败后只返回 False | 3334 会话已坏时每条命令都撞超时,驱动挂死,只能人工重启后端 |

## 2. 手册查证结论(设计依据)

- **GO**:STOPPED→GO = 从暂停点继续 ✓;CLOSED→GO = `-200 "Wrong device state"`
  (§20.5.2 原文例子);**RUNNING→GO 行为手册未涵盖**(不可依赖其报错或静默)。
- **GOS = 停止并倒回起点**,即"回到起点**并停住**",之后需要 GO 才播放
  (§20.4.3.11 + ATE AN §2.5 原文)。期望终态 = STOPPED。
- **STATE? 在 CLOSED 下正常返回 "CLOSED" 不报错**(§20.4.3.14;P0-3 已实用)。
- **STATE? 只有 7 个合法返回值**(§20.4.3.14 原文枚举):CLOSED / OPENING /
  STOPPING / STOPPED / RUNNING / EDITING / CLOSING。→ 驱动按白名单收,非法值
  (典型是会话错位读到的迟到应答 `0,"NO ERROR"`)当"没读到",不能写进真值缓存。
- **CLOSED 铁定 = 仿真已卸载**(§20.4.3.14 "Emulation has not been loaded" +
  ATE AN §2.1);而 F64 **支持本地 GUI 与远程 ATE 并发**(ATE AN §1.1),所以
  "我加载过、现在读到 CLOSED" = 别人(前面板 / 另一连接)把它关了 → 驱动应据此
  清加载态,不能继续拿旧拓扑配端口。
- **GOS + `*OPC?` 之后 STATE? 必然是 STOPPED**:GOS 不碰文件,状态机轨迹不经过
  EDITING(只能 `CALC:FILT:EDIT` 进)/ OPENING / CLOSING;STOPPING 瞬态被 `*OPC?`
  同步吃掉。→ 停止判定收严到 {STOPPED, CLOSED} 是手册支持的,**不应**为"并发瞬态"
  放宽(放宽反而会把别人正在加载的 OPENING 误判成"停住了")。
- **瞬态可持续数分钟**(OPENING "couple of minutes"),但 ATE 接口**顺序执行**,
  `*OPC?` 阻塞同步即可,不必轮询 STATE? 等稳(§20.6.1.2)。
- **`*OPC?`=1 会骗人**:只表示"执行完",不表示"没出错"(§20.6.1.2 原文警告)。
- **手册推荐的确认闭环**(§20.6.1.1-3 合成):
  `命令 → *OPC? → SYST:ERR? → 用查询命令复核真实状态`。
- **旁路与 STATE? 的关系手册未定义**:STATE? 枚举里没有 BYPASS 态;进旁路"仿真被
  暂停"、退旁路"若之前在跑则继续"。旁路下 STATE? 字面报 STOPPED 还是 RUNNING
  **只能真机验证**(记入 F64R-7 现场清单)。旁路档一律用 `MODEL:STATIC?` 另查。

## 3. 设计

### 3.1 核心:一个共享确认闭环,消掉整族"猜错误文字"

仿照 P0-3 的 `_close_and_read_state()`,抽单一入口:

```
async def _confirm_state_after(self, action: str) -> Optional[str]:
    """<命令已发> 后的手册确认闭环: *OPC? → SYST:ERR? 排读 → STATE? 复查。
    返回归一化 STATE? (或 None=读不到)。调用方持 _scpi_lock。
    错误文本只记日志/留 _last_error 参考, **判定一律以 STATE? 终态为准**。"""
```

**判定原则(整个 F64R-1 的一句话)**:命令发完后,"成没成"不看 SYST:ERR? 的文字像
不像 benign,**看 STATE? 终态是不是想要的态**:

| 调用方 | 想要的终态 | 判定 |
|---|---|---|
| `start_emulation`(GO) | `RUNNING` | STATE?==RUNNING → 成功(即使 SYST:ERR? 有 -200 幂等拒,豁免有据);≠RUNNING → fail-loud,`_last_error` 带 STATE? 实态 + 错误文本 |
| `stop_emulation`(GOS) | `STOPPED`(或 CLOSED=没加载,停的目标也算达成) | STATE? ∈ {STOPPED, CLOSED} → 成功;==RUNNING → fail-loud(真没停住);瞬态/None → fail-loud 保守 |
| `set_passthrough_mode` / `clear_passthrough_mode` | (旁路档由 STATIC? 判,已有) | 成功后**顺带回查 STATE?** 更新 `_emulation_running`,替掉内联猜(手册:进旁路暂停、退旁路可能恢复) |

现有的两处"-200 文字豁免"(GO 的 STATIC?==0 豁免、GOS 的 Wrong-device-state 豁免)
**整体删除**,由 STATE? 终态判定取代 —— 不是再加一层豁免,是换掉判定的信号源。

### 3.2 `_emulation_running` 缓存的降级定位

字段保留,但语义降为**"最近一次 STATE? 确认的快照"**:
- 写入点收敛:只在 STATE? 回读后按真值写(`== "RUNNING"`),删除各处"我猜它现在
  在跑/没跑"的内联赋值(P0-3 已收敛加载路,本项收 GO/GOS/旁路三处)。
- 读取方(监控面)见 3.3。

### 3.3 监控面用真值:`get_metrics` 每轮顺带查 STATE?

`get_metrics`(broadcaster 1 Hz 唯一轮询路)在现有查询序列里**加一条 STATE?**:
- 查得到 → `emulation_running = (state == "RUNNING")` 用真值,同时上报原始
  `simulation_state`(7 态字符串)供排障;
- 查不到 → 退回缓存值,并在 `query_errors` 标注"simulation_state: 查询失败,
  emulation_running 为缓存值"(降级可见,同 F64R-2 拓扑读路的口径);
- `get_channel_state` 同步(它已查 STATIC?,加 STATE? 对称)。

成本:每轮 +1 条查询(F64R-2 后 36 → 37),可接受;不新增节流机制(STATE? 单条
轻查询,与拓扑整段回读不同,失败也只是这一条超时,已有超时排水兜底)。

### 3.4 超时挂死升级重连

`_drain_after_timeout` 排水**也失败**(读不回任何东西 = 会话已坏)时,升级调用
既有的 `_silent_reconnect_visa()` 重建会话(懒重连基建已在,P0-1 只差这根线):
- 重连成功 → 当次命令仍返回失败(不重放命令,避免双写),但**下一条**命令可用;
- 重连失败 → 维持现状(fail-loud),日志写明"会话重建也失败,需人工介入"。
- **重建后不清任何状态快照**(⚠ 本条为 2026-07-24 提交前审查后按手册**改正**,
  评审稿原写"走 `_apply_session_reset()` 清空"是**错的**):经 NotebookLM 查证
  ATE AN §1.1 —— F64 的仿真状态住在**控制器**里不在 socket 上,只要不发 `*RST`
  (§20.4.1.8 才会 "closes the emulation"),TCP 断开重连后**运行中的仿真、已加载
  的 .smu、激活的 alignment 全部原样保留**,STATE? 照旧返回 RUNNING。按原设计清空,
  驱动会在仿真活着的时候误判"什么都没加载",端口写全线 fail-loud、拓扑白清一遍
  —— 正是 `_ensure_topology` 拼命要避免的那种误伤。socket 重连 ≠ 会话复位。
- 重建**成功**时只清一样东西:STATE? 查询的失败静默期(见 3.6),让下一拍立刻
  能读真值。这是连接健康度,不是仿真状态快照。

### 3.6 高频轮询路的两道限流(提交前审查 F1 追加)

`get_metrics` 挂在 broadcaster 的 1 Hz 轮询上,一轮要发十几条查询。仪器慢/挂死
时**每条**都会超时 → 排水 → 升级重连,于是一轮 poll 最多重建 7 次 socket(实测)。
两道限流按同一规格(30 s 静默期,与 F64R-2 拓扑读路一致):

- **会话重建冷却** `_reconnect_retry_after`:30 s 内至多重建一次。
- **STATE? 失败负缓存** `_state_query_retry_after`:上一次读失败(含读到非法值)
  后 30 s 内不再查,直接退回缓存 + `query_errors` 标注降级;**只对 `throttle=True`
  的 get_metrics 生效**,人发起的路径(GO/GOS 确认、load、旁路)一律不节流。

配套铁律:重连失败**绝不置 `_visa_resource=None`**。那是 connect() 前"从未连接"
的语义,拿它表示"重连失败"会让所有入口的 `if not self._visa_resource: return` 把
驱动短路成**永久死态**(不发命令 → 不撞超时 → 不再触发重连 → 网络恢复也不自愈)。
保留旧的半死引用,后续命令继续撞错 → 冷却窗口后再重连 → 网络一好即自愈。

### 3.5 明确不做(范围外)

- **不做**旁路态的 STATE? 语义假设:旁路下 STATE? 报什么手册没写,**真机验证**
  (F64R-7 清单已补此条)之前,旁路进出后的 running 更新按"STATE? 说什么信什么"。
- **不做** GO 前的状态预检(如 STOPPED 才发 GO):手册说 ATE 顺序执行,预检徒增
  查询;判定收口在**事后确认闭环**一处。
- **不动**加载路(P0-3 已做)、拓扑/端口(F64R-2 已做)、P1-2 其余项。

## 4. 测试计划(全部走 fake SCPI,变异自验)

- **GO 三态**:被拒 + STATE?==RUNNING → 豁免成功;被拒 + STATE?==STOPPED →
  fail-loud(**正是 #221 误豁免场景的直接回归**);无错误 + STATE?≠RUNNING →
  fail-loud(假启动,*OPC? 骗人场景)。
- **GOS 三态**:被拒 + STOPPED → 成功;被拒 + RUNNING → fail-loud;CLOSED → 成功。
- **监控面**:缓存 False + STATE?==RUNNING → 上报 True(后端重启场景);STATE?
  查不到 → 缓存值 + query_errors 标注。
- **旁路**:进旁路后 STATE? 报 STOPPED → running=False;退旁路后报 RUNNING →
  running=True(fake 按手册语义造,真机差异留 F64R-7)。
- **超时升级**:排水失败 → `_silent_reconnect_visa` 被调;重连成功当次仍 False。
- **变异自验**:删确认闭环 / 删 STATE? 判定 / 删升级重连,对应用例必须变红。

## 5. 现场依赖与风险

- `STATE?` 本身已在 P0-3 真机前提下设计并于加载路使用(手册保证实现);GO/GOS
  确认闭环只是把同一条查询移到播放控制路,**无新命令、无盲试**。
- 新增真机验证项(并入 F64R-7 现场清单):旁路(STATIC 1/2/3)下 STATE? 的字面
  返回值;RUNNING 态重复 GO 的实际行为(手册未涵盖,当前设计不依赖它)。
