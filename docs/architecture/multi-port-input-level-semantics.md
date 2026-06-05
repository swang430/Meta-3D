# 多端口输入电平 —— 操作点语义与 imbalance 门设计

> **这份文档解决什么困惑**：为什么输入电平校准用 **一个全局旋钮** 控多个端口？
> 既然一个量管不了多端口的不平衡（imbalance），**为什么不给每个端口一个独立的量**？
> 以及：把 imbalance 从"告警"升级成"通过/失败门"为什么需要**人来拍板**（语义决策）。
>
> **读者对象**：不需要读过 `input_level_controller.py` 也能看懂。深度驱动细节见
> [`f64-input-level-and-dynamic-range.md`](f64-input-level-and-dynamic-range.md)。

---

## TL;DR（先给结论）

1. **"每端口独立量"其实已经有了一半** —— F64 的 per-input **AUTOSET**（`INP:LEV:AUTOSET`
   每输入）就是每端口独立地调前端增益。但它只解决**数字化**（让每个 ADC 把信号采干净），
   **故意不改信号的真实功率**。
2. **唯一能改"真实到达功率"的旋钮是 UXM 下行功率，而它是全局单标量** —— 因为下行
   **总功率**本来就是"一个量"（小区的 DL power 是单一测试参数）。它一动就是所有端口
   一起抬/降，**消不掉端口之间的差**。
3. **能不能加一个 per-port 前向旋钮做"自动均衡"闭环？能，但那是错的设计。** 盲目把每个
   端口伺服到读数相等，会**掩盖真实故障**（坏接头本该报警，却被悄悄调平）、**分不清
   "固定线缆损耗（该补偿）"和"真实/有意的不平衡（必须保留）"**，而且用错了工具类别 ——
   固定系统性偏差应该**标定**（测一次、当已知量前馈），不是**伺服**（实时闭环）。
4. **正解 = per-port 标定 + 前馈**（roadmap `#2001 (2)(3)`）：每个端口**确实有自己的量**，
   但那是"标定常数"（现场 SA/VNA 测一次 `cable_loss_by_port_db` 落库，前馈进功率预算），
   不是闭环里乱拧的变量。补偿掉已知线缆损耗后**剩下的**不平衡才是"真问题"，交给容忍带门
   判定 + 漂移监控告警。
5. **把 imbalance 变成真门，需要你拍板**（`#2001` 门 + `#2002` 报告不确定度）：这改变
   "系统认定一次测量有效"的定义和"报告该声明多大不确定度"，属测试有效性 / 计量政策，
   不是代码细节。

---

## 1. 先理解信号链里有三个不同的"电平"

很多困惑来自把三件事混成一个"电平"。它们物理上是分开的：

```
 UXM 基站仿真器          cable           F64 信道仿真器                     probe
 (产生 N 个 DL 流) ──────────────▶  [输入口 RX] ─(数字化)─▶ [信道模型/衰落] ─▶ [输出口] ─▶ 放大器/天线 ─▶ DUT
                     每根线损耗不同        ①②                                    ③
```

| 编号 | 哪个"电平" | 谁决定 / 谁能调 | 调它改变什么 |
|------|-----------|----------------|--------------|
| ① | **数字化电平**（ADC 看到的） | F64 per-input **AUTOSET / PGA**（`INP:LEV:AUTOSET`、`INP:LEV:AMP:CH <input>`） | 只改"怎么采"，让每个 ADC 不削顶、不掉进噪声底。**不改真实功率。** |
| ② | **真实到达功率**（输入口实际 dBm） | 由 cable 损耗等物理决定；**唯一可调旋钮 = UXM DL power（全局）** | 改的是真正进系统的功率。imbalance 就出在这一层。 |
| ③ | **辐射到 probe 的功率** | F64 **输出侧** per-output（`OUTP:LOSS:SET`、`OUTP:GAIN:CH`）+ 信道模型 | 改每个 probe 辐射多少（per-probe 路损补偿，P2-10 Step 2 已做）。 |

**关键认知**：F64 是**信道仿真器**——它把输入数字化、施加信道模型、再**重新生成**输出。
所以①（数字化）和②（真实功率）是两件事：AUTOSET 把②采干净（①），但**不改**②本身
（F64 内部把 PGA 挡位映射回去，测出的 dBm 仍是②的真值；见 `#2002` 笔记）。

> **类比（频谱仪 ref level）**：设 SA 的 reference level 不会改变信号本身，只改变你"怎么看
> 它"。AUTOSET 之于 F64 输入，就像 ref level 之于 SA —— 是观测量程，不是信号功率。

---

## 2. 现在的控制环怎么工作（代码事实）

`api-service/app/services/input_level_controller.py` 的 `establish()` 闭环：

```
每轮：
  A. set_downlink_power(uxm_power)        # ← 唯一的“真实功率”旋钮，全局单标量
  C. F64 burst 模式 + 触发电平（TDD DL 必须）
  D. autoset_inputs(active_inputs)        # ← per-input AUTOSET：每端口独立调①数字化量程
  E. 测每个 input 的 avg+crest，逐个比窗口 [lo, hi-offset]
  F. clipping + cut-off 检查
  converged = (所有 input 都在窗口内) AND 不 clipping AND 不 cut-off   # ← 关键：AND 全部
  不收敛 → 整体 ±一步 UXM 功率，重试
  max_iter 轮还不行 → 整体 FAIL（“N 轮未收敛”）
```

注意：**第 D 步已经是 per-port 的**（AUTOSET 每输入独立）。所以"给每个端口独立量"在
①数字化这一层**早就实现了**。问题不在这里。

---

## 3. 为什么"一个全局量管不了多端口"

4×4 各 input 走不同 cable/port，②真实到达功率天生有 **±1–2.5 dB 散布**，分项（`#2001`）：

| 来源 | 量级 |
|------|------|
| cable 长度 / 质量差异 | ±0.5–1 dB |
| UXM TX port 间差异 | ±0.3 dB |
| F64 ADC 增益差异 | ±0.5 dB |
| 接头老化 | ±0.2 dB |
| 测量噪声 | ±0.1–0.3 dB |

控制器要让 E 步**所有** input 同时进窗口，但它只有 UXM 这**一个全局**旋钮，一动就是
全体平移，**消不掉端口之间的差**。于是只要散布够宽，**不存在任何单一全局功率**能让每个
端口同时进窗口 → 循环耗尽 → FAIL。其实啥毛病没有，纯物理；0.3 dB 边缘越界也照死。
这就是当前 strict 门"不科学"的地方。

---

## 4. 正面回答：为什么不给每个端口一个独立的量？

这是本文核心。答案分四层，**你的直觉是对的，但"独立量"该是标定常数，不是闭环变量**。

### 4.1 ①数字化层：已经是 per-port 了

AUTOSET（`INP:LEV:AUTOSET <input>`）就是每端口独立把 ADC 量程调好。这一层不需要再加东西。

### 4.2 ②真实功率层：per-input PGA **故意**不能改它 —— 这是对的

F64 的 `INP:LEV:AMP:CH <input>` 看起来是"每端口一个电平旋钮"，但它调的是①（前端 PGA
量程），**不改②真实到达功率**（F64 映射回真值）。这是**有意设计**：

> ②（流与流之间的真实相对功率）**是你要测量的量本身**。你不能用一个旋钮把"被测量"
> 偷偷改掉 —— 那等于先动了考卷答案再判分。

所以在②这一层，**没有**一个"免费的"per-port 旋钮，这是**故意的**，不是疏漏。

### 4.3 唯一改②的旋钮（UXM DL power）为什么本就该是全局一个量

下行**总功率**是"小区给 DUT 多大下行"——这本身是**单一测试参数**（TestCase 指定）。它
就应该是一个量。端口**之间的差**是另一回事，不该由"总功率"这个旋钮负责。
（注：我们的 HAL 只暴露全局 `set_downlink_power(dbm)`；即便将来加 per-port UXM TX 功率，
它也会和"有意的流间功率比"耦合 —— 那也是测试参数，不是可随便拧的均衡旋钮。）

### 4.4 那加一个 per-port 前向旋钮（如 `OUTP:GAIN:CH`）做"自动均衡闭环"行不行？

**物理上能**（F64 输出侧确有 per-output 旋钮）。**但作为"伺服到读数相等"的盲环是错的设计**，
三个理由：

1. **会掩盖真实故障**。盲目把每端口调到读数相等，等于把"端口 4 低 3 dB"这个信号擦掉 ——
   可如果那 3 dB 是**接头坏了**呢？本该报警的硬件故障被悄悄调平、永远发现不了。
   （`#2001 (3)` 漂移监控存在的意义正是抓这个。）
2. **分不清"该补偿"和"该保留"**。3 dB 里多少是固定线缆损耗（该补偿）、多少是真实/有意的
   信道不平衡（必须保留）？**实时闭环没有 ground truth**，只有一次独立测量（SA/VNA）才知道。
3. **用错了工具类别**。固定的系统性偏差（线缆损耗）应该**标定**（测一次、当已知量前馈），
   不是**伺服**（实时闭环）。实时环是用来跟"测试中会漂的量"的；线缆损耗不会快速漂。
   对一个静态偏差做实时伺服，等于亲手毁掉故障可检测性。

### 4.5 正解：per-port **标定 + 前馈**（= `#2001 (2)(3)`）

每个端口**确实有自己的量** —— 但它是**标定常数**：

- **(2)** 现场用 SA/VNA 把每个 port 的 `cable_loss_by_port_db` 测一次，落成一个标定证书
  `CableBalanceCalibration`；上游 feed-forward 用 per-port 实测值**取代**现在的 chamber 平均。
- 补偿掉已知线缆损耗后，**剩下的**不平衡 = 没法解释的 = 真问题 → 交给容忍带门判定。
- **(3)** 持续监控这个 per-port 量，N 次差异中位数 > 阈值 → 主动告警操作员（线缆/接头在退化）。

这就是你说的"每端口独立量"，只是落成"**标定常数前馈**"而不是"盲环变量"——
既补偿了物理必然的偏差，又**保住了发现故障的能力**。这也是 CTIA MPAC OTA 的标准做法。

> **为什么不能纯本地做完**：(2) 需要现场 SA/VNA 实测每根线的损耗才能填那张表。没有它，
> "软化门"只是把真问题藏起来；有了它才是合法补偿。所以这件事 = **你的政策决定 + 一次
> 现场测量**，两个前提缺一不可。这也是 `#143` 当时只做"纯遥测、不碰 converged/fail"的原因。

---

## 5. 待你拍板的语义决策

`#143`（已合并）只加了 **imbalance 遥测**：算 `imbalance_db = max(avg) − min(avg)`、分
`ok ≤1 / marginal ≤2.5 / excessive >2.5 dB` 容忍带、marginal/excessive 加 `system_warning`，
但**不改 converged/fail 门**。把它从"告警"升级成"真门"要你定下面几件事 —— 都属测试
有效性 / 计量政策，代码层替不了：

1. **通过判据**：保持"每 input 绝对进窗口"（现状，严）？还是改"组平均进窗口 + imbalance ≤
   容忍带"（放松单 input 绝对要求）？后者等于宣布"我容忍 ~2 dB 散布是物理正常"。
2. **绝对 vs 相对**：软化后单端口绝对电平不再各自卡窗口，只看组平均 + 散布。对你要做的测量
   （吞吐容忍几 dB vs 绝对功率/RSRP 精度敏感）能不能接受？
3. **容忍带数字哪来**：`ok≤1 / marginal≤2.5 / excessive>2.5` 是**占位估计**。要变真门，
   这几个数应来自标准（CTIA MPAC OTA）或实验室政策。
4. **不确定度入报告（`#2002`）**：现在报告把 RSRP/吞吐当确定值（"RSRP ±0" 是骗人的）。
   AUTOSET 操作点继承 F64 出厂 ADC cal 的 ±0.5–1 dB + 单次测量噪声 ±0.3 dB。要不要按 GUM
   累加进 combined uncertainty（k=2）报出来？**且跟门耦合**：容忍越大散布，报告该声明的
   U 越大 —— 软门和报不确定度不能只动一个，否则报告不自洽。

---

## 6. `#2001` vs `#2002` —— 同一个"操作点语义"的两面

| | 管什么 | 子项 | 状态 |
|--|--------|------|------|
| **`#2001`** | 操作点的**接受侧**："我接受什么样的电平" | (1) imbalance metric + 容忍带 | ✅ `#143`（纯遥测） |
| | | (2) per-port cable balance cal + 前馈 | ⏳ 待决策 + **现场** SA/VNA |
| | | (3) 漂移监控告警 | ⏳ 长期 |
| **`#2002`** | 操作点的**声明侧**："我为此声明多大不确定度" | 操作点不确定度按 GUM 累加进报告 combined U | ⏳ 待决策 + 现场真值 |

两个边界记录（来自 `#2002`）：

- **严格 PFS / PWS 未来场景**：AUTOSET 改 PGA 可能引入 group-delay → phase shift，须 cal 后
  不动 PGA 或 re-cal phase。当前 power-only PFS 不受影响（TR 37.977 F.2）。
- **VRT 跨场景切 cell config**：PAPR 漂 → 操作点需 re-setup（VRT 当前未接 InputLevelController，
  接入时一起做）。可加 idempotency gate（setup 过 + 同 cell config 跳过）防 azimuth loop 内
  误调 AUTOSET 污染跨 azimuth 可比性。

---

## 7. 现状 / 前置条件一览

| 项 | 能不能现在本地做 | 卡在哪 |
|----|------------------|--------|
| imbalance 遥测（指标 + 容忍带 + 告警） | ✅ 已做（`#143`） | —— |
| 软化 converged/fail 门改用 imbalance 带 | ❌ | 需 (1) 你定判据/阈值语义 + (2) per-port cable cal |
| per-port cable balance cal 落库 | ❌ | 现场 SA/VNA 实测每根线损耗 |
| 报告 combined uncertainty（GUM, k=2） | 半 | 需你定计量政策 + 现场标定真值 |

---

## 8. 参考

- 深度子系统设计（F64 前端模型 / burst 测量条件 / 闭环 SCPI / 分方向策略）：
  [`f64-input-level-and-dynamic-range.md`](f64-input-level-and-dynamic-range.md)
- TestCase 单一真值源驱动架构（操作点属同族）：
  [`testcase-driven-instrument-config.md`](testcase-driven-instrument-config.md)
- roadmap backlog：`docs/roadmap-first-call.md` 的 `#2001` / `#2002` 条目；P2-11 Phase 6
  "DL power" 即结合本操作点坑。
- 代码位置：
  - 控制环：`api-service/app/services/input_level_controller.py`（`establish` / `_classify_imbalance`
    / `_measure_and_check_window`）
  - F64 驱动旋钮：`api-service/app/hal/propsim_f64.py`
    （`autoset_inputs` / `set_baseband_power` = `INP:LEV:AMP:CH`；`set_output_path_loss` /
    `set_output_gain` = `OUTP:LOSS:SET` / `OUTP:GAIN:CH`）
  - UXM 全局功率：`api-service/app/hal/uxm_base_station.py`（`set_downlink_power`，单标量）
