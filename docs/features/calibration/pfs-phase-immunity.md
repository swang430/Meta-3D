# PFS Phase Immunity — 为什么 3GPP TR 37.977 不要求 chamber-path phase 校准

> **文档目的**：解释 PFS-mode MPAC 为什么对 per-probe chamber 相位误差天然免疫，
> 以及这个免疫性在什么情况下失效。同时记录本项目的 phase-calibration 基建为什么
> 仍然保留（PWS 模式将来需要）。
>
> **读者**：未来翻代码看到 `probe_phase_calibrations` 表 / `PhaseCalibrationService` /
> CAL-04 但没看到任何地方在 PFS 路径上用它的人 —— 不是 dead code，是为 PWS 留的。
>
> 配套阅读：[`probe-calibration.md`](probe-calibration.md) §4（phase calibration 实施方法）、
> [`IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md)。

---

## 1. 背景

2026-05-17 项目内部对 P1-5 (CAL-04 phase calibration) 是否值得做出过一次架构讨论。
争议点：**3GPP TR 37.977 / CTIA 01.40 实际上要求哪些 phase 校准？**

查证结论（详见 §6 引用）：

- **3GPP TR 37.977** 的 normative MPAC calibration（Annex F.2）**纯功率校准，不包含相位**。
  Annex B.1 不确定度预算 38 行全部以 dB 为单位，没有 per-probe phase error 这一行。
  Rel-14 → Rel-19（2025-10）F.2 文字完全一致。
- **CTIA 01.40 V6.0.1** 有 normative "shall" 的 phase calibration（§2.2.2.3 + §4.2.5），
  容差 180°±5°，但**只覆盖 BS simulator → CE 输入之间的相位对齐**，不覆盖 chamber path。
- 各 CE 厂家（Keysight、R&S、Spirent）讲的 "phase calibration" 也是 CE 内部 / AIU 端口对齐，
  scope 跟 CTIA §2.2.2.3 一致，不涉及 chamber path。

也就是说，**没有任何 normative spec 要求 CE 出口到 probe 振子到 DUT 之间这一段做 per-probe 相位校准**。
项目本身 hardware 链路里的 amp/atten 漂移也确实导致这段相位"测了即过时"。

但是 —— 这个免疫**不是 spec 写得宽松，是 PFS 这个合成方法本身的数学性质**。
理解这个性质对项目后续做架构选择（特别是 PWS 模式扩展）非常关键，所以单开本文档详细推导。

---

## 2. PFS vs PWS at a glance

| 维度 | PFS (Prefaded Signal Synthesis) | PWS (Plane Wave Synthesis) |
|------|------|------|
| 标准 | 3GPP TR 37.977 §6.3.1.1 default MPAC | 不是 3GPP TR 37.977 default；3D MPAC / VCOMP 等场景使用 |
| 合成对象 | DUT 处的 **二阶统计量**（spatial correlation matrix） | DUT 处的 **瞬时电磁场**（确定性平面波） |
| Per-probe 信号 | **独立 fading 序列**（probe 间时域正交） | **共享 baseband × 复数权重**（probe 间相干） |
| Per-probe chamber phase 误差 | **数学免疫**（详见 §3 推导） | **直接污染合成波前**，必须 cal |
| 校准要求 | 仅 power（TR 37.977 §F.2） + CE 内部 phase（CTIA §2.2.2.3） | 全 chamber path per-probe phase + amplitude cal |

本项目**当前**默认运行在 PFS 模式（3GPP TR 37.977 范畴）。**未来**计划扩展 PWS 模式（参见 [roadmap-first-call.md](../../roadmap-first-call.md) P1-5 / CAL-04 的 PWS 注解）。

---

## 3. PFS 为什么对 per-probe phase 免疫 —— 数学推导

### 3.1 系统模型记号

- N 个 probe（典型 8、16、32），DUT 有 2 根天线（m、n 索引）
- L 个 cluster（multipath 簇），每个 cluster 在 PAS 上对应一组 sub-ray
- Probe i 在 cluster l 上发的信号：

$$
x_{i,l}(t) = \sqrt{P_{i,l}} \cdot h_{i,l}(t) \cdot s(t-\tau_l)
$$

  - $P_{i,l}$：per-probe per-cluster 功率系数（CE 离线算好的，让 DUT 处合成 PAS 等于目标）
  - $h_{i,l}(t)$：fading sequence，零均值复高斯
  - $s(t-\tau_l)$：cluster l 的时延信号

- Probe i 总输出：$x_i(t) = \sum_l x_{i,l}(t)$
- DUT 天线 m 接收：$y_m(t) = \sum_i a_{m,i} \cdot x_i(t)$
  - $a_{m,i}$：probe i 到 DUT 天线 m 的几何 / 自由空间耦合（实数 + 已知）

### 3.2 PFS 的关键设计选择：probe 间 fading 独立

PFS（Prefaded Signal Synthesis）—— "prefaded" 就是说 fading 不在 RF 路径里实时叠加，
而是在 CE 内部**提前**生成好每个 probe 各自的 fading 序列。**关键性质**：

$$
E\left[h_{i,l}(t) \cdot h_{j,l'}^*(t)\right] = \delta_{ij} \cdot \delta_{ll'} \cdot \sigma_h^2
$$

- $i = j, l = l'$：同 probe 同 cluster，方差 $\sigma_h^2$
- $i \neq j$ 或 $l \neq l'$：**互不相关**（独立复高斯）

特别地：$E[x_i(t) \cdot x_j^*(t)] = 0$ 当 $i \neq j$，即 **probe 间信号时域正交**。
这是 PFS 这个名字背后真正的数学含义，也是它对 chamber 相位免疫的根源。

### 3.3 加入 chamber 相位误差

实际硬件上，CE 出口到 DUT 之间每一路有一个未校准的 chamber 相位 $\varphi_i$（cable + amp + atten + connector 全部累加）。等效于：

$$
a_{m,i} \to a_{m,i} \cdot e^{j\varphi_i}
$$

DUT 处空间相关矩阵：

$$
R_{m,n} = E\left[y_m(t) \cdot y_n^*(t)\right]
= E\left[\sum_i a_{m,i} e^{j\varphi_i} x_i(t) \cdot \sum_j a_{n,j}^* e^{-j\varphi_j} x_j^*(t)\right]
$$

展开求和：

$$
R_{m,n} = \sum_{i,j} a_{m,i} a_{n,j}^* \cdot e^{j(\varphi_i - \varphi_j)} \cdot E\left[x_i(t) \cdot x_j^*(t)\right]
$$

### 3.4 关键消解步骤

代入 PFS 的正交性 $E[x_i \cdot x_j^*] = 0$ for $i \neq j$，**只有 $i = j$ 项存活**：

$$
R_{m,n} = \sum_i a_{m,i} a_{n,i}^* \cdot \underbrace{e^{j(\varphi_i - \varphi_i)}}_{= 1} \cdot E\left[|x_i(t)|^2\right]
$$

$$
= \sum_i a_{m,i} a_{n,i}^* \cdot \sum_l P_{i,l}
$$

$e^{j(\varphi_i - \varphi_i)} = e^{j \cdot 0} = 1$ —— **per-probe 常数相位完全消失，achieved $R_{m,n}$ 跟没有 chamber 相位误差时一字不差**。

吞吐量、CTIA OTA KPI 关心的二阶统计量看到的 spatial correlation matrix 跟 chamber 相位无关。
amp/atten 漂移引入的 $\varphi_i$ 不论多大，对这个量贡献 0。

### 3.5 PWS 为什么是另一回事

PWS 要合成**瞬时**的确定性平面波（不靠统计量、靠相干叠加）。Per-probe 信号是：

$$
x_i(t) = w_i \cdot s(t)
$$

—— 共享同一个 baseband $s(t)$，权重 $w_i$ 是 CE 算好的复数。这是**相干 coherent** 而非 PFS 的 orthogonal。

那么 cross-probe term $i \neq j$ 不再为零，DUT 处：

$$
y_m(t) = \sum_i a_{m,i} \cdot e^{j\varphi_i} \cdot w_i \cdot s(t)
$$

$e^{j\varphi_i}$ **直接进 beamforming sum**，瞬时波前形状被破坏。所以 PWS 必须做 per-probe phase cal —— 不是 spec 要求，是数学要求。

---

## 4. 免疫性失效的几种情况

PFS 的相位免疫不是无条件的。下面这几种情况要警惕：

### 4.1 Probe 间 fading 不独立（实现错误）

如果 CE 实现偷懒，让所有 probe 共享一个 cluster fading $h_l(t)$，然后乘以复数权重 $w_{i,l}$：

$$
x_i(t) = \sum_l w_{i,l} \cdot h_l(t)
$$

那 $E[x_i \cdot x_j^*] = \sum_l w_{i,l} \cdot w_{j,l}^* \cdot \sigma_h^2 \neq 0$，cross-probe term 不消，per-probe phase 又开始污染合成场。**这不是 PFS，是退化成了类 PWS 的实现**。

这是不能假装看不见的问题。本项目实现状态见 §5。

### 4.2 Chamber phase 在单次 fading 实现内时变

PFS 数学要求 $\varphi_i$ 是**常数**。如果 amp 在测试过程中温漂导致 $\varphi_i(t)$ 变化，那 §3.4 的消解变成：

$$
e^{j(\varphi_i(t) - \varphi_i(t'))} \neq 1 \quad \text{当} \quad t \neq t'
$$

这会引入额外 decorrelation，搞坏 Doppler 谱。所以：
- **常数相位偏移**：免疫
- **慢变温漂（mins-hours 时间尺度）**：实际上还是常数（在单次测试 ~seconds 时间内），免疫
- **快速热漂（sub-second 内）**：不免疫 —— 这种情况下需要工程上保证 amp / chamber 温稳定

这是为什么 phase cal 本身**意义有限**但 amp 的**热稳定性 / 长期老化补偿**还是重要的。

### 4.3 频率相关 dispersion

如果 $\varphi_i(f)$ 在工作带内有大幅倾斜（cable 长度差 + amp group delay 差），等效于一个 frequency-selective fading 叠加到 channel model 上，会被 CE 的 channel model 吸收得不干净 —— 部分泄漏到 DUT 侧的 PDP（power-delay profile）。

TR 37.977 §F.2 的 power 校准本身没管这个，靠 amp 是 wideband 平的 + cable 长度差有限来保证。这是个**实施级别的工程问题**，不是 PFS 数学免疫的反例（数学层面 $\varphi_i$ 在某个特定频点上仍然消解），是 implementation reality。

### 4.4 PWS / 任何 coherent 合成

如 §3.5 所示。任何走相干合成路径的模式，免疫不成立，必须 per-probe phase cal。

---

## 5. 本项目实现状态 ⚠️

> **2026-05-17 调研结果**：本项目自身**不实现 fading 生成器** —— 由 vendor CE 硬件内部完成。
> Per-probe fading 是否独立是 vendor CE 的实现属性，本项目代码不可见。

### 5.1 本项目代码做了什么

1. [`ChannelEgine/channel_model_38901/channel_generator.py`](../../../../ChannelEgine/channel_model_38901/channel_generator.py)（外部 repo）
   计算 channel realization：每个 cluster 一个 IID 复高斯矩阵 $H_{iid}$，乘 Cholesky 染色 $L_{rx} \cdot H_{iid} \cdot L_{tx}^H$。这是 **per-cluster 一个 fading 实现**，不是 per-(probe, cluster)。

2. `channel-engine-service/.../channel_engine.py` 给每个 probe 算一组复数权重 `(weight_magnitude, weight_phase)`，输入是 cluster 的 AoA / AoD / 功率：
   ```python
   weight_magnitude, weight_phase = self._compute_single_probe_weight(
       probe_theta=probe_pos.theta,
       probe_phi=probe_pos.phi,
       cluster_aoa_deg=cluster_aoa_deg,
       cluster_powers=cluster_powers
   )
   ```
   注意：返回的是**复数权重**（带 phase），形式上是 PWS-leaning 的。

3. 输出 `.asc` TDL 波形文件 + per-probe scaling，上传到 F64 (Keysight PROPSIM)。
   实际 fading **多路输出**由 F64 内部的 fading filter bank 完成。

### 5.2 关键 open question — F64 内部是不是 per-port 独立 fading？

**不知道**。Keysight F64 PROPSIM 的内部 fading 滤波器组实现是黑盒：

- 行业惯例 + Keysight 是 CTIA / 3GPP 认证 lab 主力 CE → 强假定它内部做 per-port 独立 fading（否则过不了 CTIA spatial correlation validation）
- 但这是**间接推论**，不是文档证据
- `.asc` 文件格式 + F64 runtime 把 per-probe scaling 跟 fading filter bank 是怎么组合的，我们没有 Keysight 内部文档

### 5.3 风险评估

| 假设 F64 内部 per-port fading | 本项目 PFS 数学有效性 | 风险 |
|---|---|---|
| 独立（行业默认 + 推论） | 有效 —— per-probe phase 免疫成立 | 低 |
| 共享 + 权重（退化 PWS 实现） | 无效 —— per-probe phase 直接污染 | 高，但目前无证据指向这个情况 |

**建议（不阻塞 first-call）**：
- 下次去现场时跟 Keysight FAE 或者 CAICT 认证侧的人确认一下 F64 PROPSIM 内部 fading filter bank 的拓扑
- 或者做一个 controlled 实验：固定 channel model，故意给两个 probe 加不同的 chamber 相位偏移，看 DUT 处 spatial correlation 是否真的不变 —— 不变 = 假设成立，变 = F64 内部不是 per-port 独立 fading
- 在 §5.2 这个 open question 解决之前，**保留 phase cal 基建**作为对冲

---

## 6. References

### Spec 出处

- **3GPP TR 37.977 V19.0.0**（Rel-19，2025-10）—— Verification of radiated multi-antenna reception performance of UE
  - §F.2 MPAC calibration procedure（power-only）
  - §B.1 MPAC uncertainty budget（无 per-probe phase 项）
  - §12.1.4.3 Calibration（"signal level only"）
  - §8.3.2.3 Spatial correlation validation
  - §6.3.1.1 default MPAC method（PFS）
- **3GPP TR 37.977 V14.3.0 / V18.0.0** —— F.2 / B.1 文字与 V19 完全一致，确认从 Rel-14 起 phase cal 一直未被纳入 normative requirement
- **CTIA 01.40 V6.0.1** —— Test Methodology for MIMO Multi-Probe Anechoic Chamber
  - §2.2.2.3 Channel Emulator Input Phase Calibration（"shall"）
  - §4.2.5 Input Phase Calibration Validation（180°±5° normative tolerance）

### 项目内部

- [`docs/features/calibration/probe-calibration.md`](probe-calibration.md) §4 Phase Calibration（实施方法 + 数据库 schema）
- [`docs/features/calibration/IMPLEMENTATION-PLAN.md`](IMPLEMENTATION-PLAN.md) CAL-04 phase calibration 实施计划
- [`docs/roadmap-first-call.md`](../../roadmap-first-call.md) P1-5 — CAL-04 phase calibration
- [`api-service/app/models/probe_calibration.py`](../../../api-service/app/models/probe_calibration.py) `ProbePhaseCalibration` ORM
- [`api-service/app/services/probe_calibration_service.py`](../../../api-service/app/services/probe_calibration_service.py) §`PhaseCalibrationService`（line 638+）

### 学术 / vendor 资料

- IEEE 论文：VCOMP / PWS / 3D MPAC 相关 phase-cal 必要性论证（见调研记录）
- Keysight PROPSIM / R&S SMW / Spirent E2010 vendor 文档 —— "phase calibration" 范畴均为 CE 输入 / AIU 端口对齐，与 CTIA §2.2.2.3 同
