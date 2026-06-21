> ⚠️ **本文档(V0.1)已被 [`RT-MPDB-CDL-F64-channel-injection-design_V1.0.md`](RT-MPDB-CDL-F64-channel-injection-design_V1.0.md) 取代。**
> V0.1 的 `f_D,max` 级联判决在后续讨论中被"按角度聚类使 native 可表示 → B-2 普及"突破降级为附录;
> 完整设计(含 MPDB 多聚类 + 标注式 CDL 参数结构 + 确定性双路)见 V1.0。本文保留作历史。

---

# B-1 / B-2 信道注入路径判决设计（V0.1 草案，已被 V1.0 取代）

| 字段 | 值 |
|---|---|
| 性质 | 设计草案，供 review |
| 版本 / 日期 | V0.1 / 2026-06-21 |
| 关联产品 | Lauraycs（射线追踪）→ ChannelEgine（信道合成）→ MIMO-First（编排 + F64 驱动） |
| 上游文档 | `docs/hardware/PROPSIM_F64_信道注入工程文档_A-B路线_SCPI_V1.4_1.docx`（§7/§9/§10）；`docs/design/RT-ChannelEgine-MIMOFirst_B2打通实施方案_V1.0.pdf` |
| 证据基础 | 本轮 PROPSIM 手册深挖（User Reference Rev 10.2 / Channel Studio GCM Rev 15.0 / Runtime Emulation / Multi-emulator sync）+ NotebookLM 侧方案共识 |
| Roadmap | 待对齐（属 B-2 打通 / 信道注入主线，与 P2-11 GCM .smu 联动相邻）—— 本文为设计件，非代码改动 |

---

## 0. TL;DR

给定一个 MPDB 导出的 CDL 场景，本设计用一个**级联判决函数**把它**整场景**判给 **B-1（确定性 CIR 烘焙回放）** 或 **B-2（参数化 TDL + F64 硬件实时衰落）**，**二选一、不在场景内混合**。

- **主边界参数 = `f_D,max`（场景最大多普勒频移 = v_max·f_c/c）**，阈值 `f_D,max,crit = f_upd,max/(2·SD)`。
- **B-2 的多普勒保真**靠自研算法：**双高斯拟合 + >2 峰联合域分裂**，在 F64 仅有的闭式谱上逼近 RT 的定制 per-cluster Doppler PSD（F64 无任意 PSD 参数接口，已证实）。
- 判决产出一个 `engine_mode`，作为 TestCase 单一真值源的一部分，**fail-loud** 驱动下游 ChannelEgine 合成与 F64 加载。

---

## 1. 背景与既定前提（本轮调研收口）

三条已被手册级证据钉死的事实，是本设计的地基：

1. **F64 没有"任意定制多普勒扩展谱"的参数接口。** 参数化硬件衰落只有封闭谱集（`Classical/Flat/Pure Doppler/Rice/Nakagami/Lognormal/Suzuki/Gaussian双beam` + `Custom`=6谱形×3幅度分布）；**任意采样点 PSD 只能离线烘成 CIR 走 `.asc/.ir` 回放**（User Reference Rev 10.2，全文无 user-defined PSD / 无 `.tdlx`）。
2. **B-1 与 B-2 各有物理边界，谁都不能独吞全场景空间**：
   - **B-1 受奈奎斯特/文件经济硬限**：烘焙可表示多普勒 = `f_upd,max/2`，高 `f_D,max`（高速 × 高频，尤其 FR2 车载以上）烘不动 / 文件爆炸。
   - **B-2 受 F64 闭式谱限**：拿不到 RT 任意 PSD，须**逼近**。
3. **变通使 B-2 在多数情况下仍可用**：双高斯拟合（单峰非对称/双峰）+ >2 峰联合域分裂（拆成 ≤2 模子簇），让定制 PSD 落到 F64 原生 `Gaussian` 谱上，**保住 B-2 的低更新率收益（~100Hz 几何骨架率）**。

**核心架构约束（用户确立）**：**一个场景只能选一个方式（B-1 或 B-2），不混合。** 因为 F64 的 `.asc/.ir`（CIR 回放模型）与 `.tap/.tdlx`（参数化衰落模型）是**不同的模型类型**，同一逻辑通道 / 同一份 `.smu` 不并存两种生成机制；按场景一次判决最干净、可审计。

---

## 2. 判决输入

判决函数 `decide_path(scenario, f64_profile, test_intent) -> PathDecision`。三类输入：

### 2.1 场景结构（MPDB 导出的 CDL）
| 字段 | 含义 | 用途 |
|---|---|---|
| `clusters[]` | 每簇 `{τ, P, AoA/AoD/ZoA/ZoD, AS_*, XPR, K}` + **per-cluster 子径集（角度,功率）** | 算每簇 Doppler PSD；B-2 拟合/分裂 |
| `n_clusters` | 簇数 | tap 预算核算 |
| `n_links` | 逻辑通道数 = f(Tx, Rx, **N_probe**) | 文件体积估算 |
| `route_len_D` | 路由长度（m） | 文件体积估算（CIRs 数） |

### 2.2 场景运动学
| 字段 | 含义 |
|---|---|
| `v_max` | 场景最大相对速度（m/s） |
| `f_c` | 载频（Hz） |

> `f_D,max = v_max · f_c / c` 由这两个量决定，**是场景级标量**（全簇共用同一 v_max、f_c）—— 这与"一场景一路径"天然吻合：主边界参数本身就是场景级。

### 2.3 F64 能力档（`f64_profile`，⚠️ 多项需现场标定，见 §7）
| 参数 | 缺省（待验证） | 含义 |
|---|---|---|
| `f_upd_max` | 10 kHz（假设） | 文件回放最大 CIR 更新率 → 决定 B-1 临界 |
| `SD` | 2 | 采样密度（每半波长采样数） |
| `tap_budget` | 24（运行时）/ 48（ASC） | 每逻辑通道最大抽头 |
| `delay_resolution` | 5 / 10 / 20 ns | 硬件时延分辨率 → 限分裂粒度 |
| `rho_thresh` | 待标定 | 双高斯拟合残差验收阈（绑 BER/吞吐灵敏度） |
| `file_budget` | 待定（运维） | 单场景 B-1 文件体积上限 |
| `gaussian_model_available` | 待验证 | 现场 Channel Studio/固件是否有 `Gaussian` 双beam 谱 |

### 2.4 测试意图（来自 TestCase）
| 字段 | 含义 |
|---|---|
| `requires_deterministic_phase` | 是否需确定性逐实现相位（波束跟踪 / ISAC / 高保真空间）。B-2 仅统计相位，无法满足 → 该意图强制 B-1/GCM |

---

## 3. 边界参数定义

### 3.1 主边界：`f_D,max` 与临界 `f_D,max,crit`
```
f_D,max      = v_max · f_c / c                      # 场景最大多普勒（扩展半宽上界）
f_D,max,crit = f_upd_max / (2 · SD)                 # B-1 烘焙的奈奎斯特临界
```
- 物理依据：B-1 把多普勒烘进 CIR，须 `f_upd = 2·SD·f_D,max ≤ f_upd_max`；可无失真表示的最大多普勒 = `f_upd_max/2`（详 V1.4 §4.0）。
- 缺省临界（10 kHz / SD=2）≈ **2.5 kHz**；工程取 **2 kHz** 留安全裕度。
- **判据**：`f_D,max > f_D,max,crit` ⟹ B-1 在扩展维度上**不可行** ⟹ 必走 B-2。

### 3.2 辅边界 1：文件经济性（常先于奈奎斯特触发）
```
CIRs_total   = 2 · SD · route_len_D / λ  = 2 · SD · route_len_D · f_c / c   # 注意：与速度无关
FileSize_B1  ≈ CIRs_total · n_links · n_taps · BYTES_PER_COMPLEX_TAP
```
- **关键洞察**：所需 CIR 快照数 `CIRs_total = 2·SD·D/λ` 只与**路由长度 / 波长**有关，**与速度无关**。长路由 × 高频（小 λ）→ 快照数爆炸，即便 `f_D,max` 在奈奎斯特窗内也能撑爆文件。
- **判据**：`FileSize_B1 > file_budget` 或 `CIRs_total > 格式上限`（.asc 通常 ≤ ~1e6）⟹ B-1 **不经济** ⟹ 走 B-2。

### 3.3 辅边界 2：B-2 可表示性（双高斯拟合 + 分裂的产出）
```
ρ_max            = max_i  normalized_residual( S_i_RT , S_i_F64fit )   # 各簇 Doppler PSD 拟合残差的最大值
n_taps_after_split = Σ_i  taps(i)  （分裂后总抽头）
```
- **判据**：`B2_representable ⟺ (ρ_max ≤ rho_thresh) AND (n_taps_after_split ≤ tap_budget)`。
- 算法见 §5。

### 3.4 覆盖输入：确定性相位意图
- `requires_deterministic_phase == True` ⟹ B-2 被排除（统计相位），落 B-1（可行时）或 GCM。

---

## 4. 判决函数（级联，确定性、可审计）

以 `f_D,max` 为主，级联四阶。**先意图覆盖、再可行性强制、最后偏好策略**。

```python
def decide_path(scenario, prof, intent) -> PathDecision:
    f_D_max  = scenario.v_max * scenario.f_c / C
    f_D_crit = prof.f_upd_max / (2 * prof.SD)            # ≈2.5kHz@10k/SD2

    # ── Stage A：测试意图覆盖（确定性相位）──
    if intent.requires_deterministic_phase:
        return B1 if b1_feasible(scenario, prof) else ESCALATE_GCM
        # B-2 统计相位，不满足确定性相位需求

    # ── Stage B：主可行性门（f_D,max 奈奎斯特）──
    if f_D_max > f_D_crit * SAFETY:        # 扩展太快，烘不动
        return _b2_or_escalate(scenario, prof)

    # ── Stage C：辅可行性门（文件经济），仅在 f_D,max 通过时 ──
    if file_size_b1(scenario, prof) > prof.file_budget:
        return _b2_or_escalate(scenario, prof)

    # ── 至此 B-1 既可行又经济 → 默认 B-1（最高保真，无 PSD 近似）──
    return B1


def _b2_or_escalate(scenario, prof) -> PathDecision:
    fit = recluster_and_fit(scenario.clusters, prof)     # §5：双高斯 + 联合域分裂
    if fit.rho_max <= prof.rho_thresh and fit.n_taps <= prof.tap_budget:
        return B2(fit)                                   # 携带 tap 参数/分裂结果
    return ESCALATE                                       # GCM / 拆子路由 / 签字接受残差
```

### 4.1 判决表（速查）

| `f_D,max` vs crit | 文件经济 | B-2 可表示 | 需确定性相位 | **判决** |
|---|---|---|---|---|
| ≤ crit | ✅ 经济 | — | 否 | **B-1**（默认，保真） |
| ≤ crit | ❌ 超预算 | ✅ | 否 | **B-2** |
| ≤ crit | ❌ 超预算 | ❌ | 否 | **ESCALATE**（GCM/拆路由） |
| > crit | — | ✅ | 否 | **B-2**（奈奎斯特强制） |
| > crit | — | ❌ | 否 | **ESCALATE** |
| ≤ crit | ✅ | — | **是** | **B-1**（确定性相位） |
| > crit | — | — | **是** | **ESCALATE_GCM**（B-1 不可行且 B-2 无确定性相位） |

> **设计取向**：B-1 可行时**默认 B-1**（其 PSD 是 RT 子径求和的**精确**值，无近似；且可给确定性相位）。**B-2 是 B-1 撞边界后的逃生路径**，靠 §5 算法在 F64 闭式谱上**逼近** RT PSD。两者都保留、按边界二选一，正是用户要的"都要、各有边界、不混合"。

### 4.2 与"一场景一路径"的一致性
- Stage B 的 `f_D,max` 是场景级标量 → 主门天然按场景判一次。
- 各簇差异只体现在 **PSD 形状**（角扩展不同），只进 §5 的 B-2 可表示性（拟合/分裂），**不影响主门**。
- 故"主门按场景、形状进算法"两层干净分离，绝不产生场景内混合。

---

## 5. B-2 可表示性算法：双高斯拟合 + 联合域分裂（自研核心 IP）

目的：把 RT 每簇的定制 Doppler PSD 映射到 F64 能参数化生成的形态，并核算 tap 预算与残差。**位于 ChannelEgine 合成层**，是现有 RT→簇降维聚类的 **Doppler-aware 扩展**。

### 5.1 逐簇流程
对每个簇 `i`（含 RT 子径 `{(θ_m, p_m)}`）：

1. **建经验 Doppler PSD**：`f_D,m = (v/λ)·cosθ_m`；`S_i(f) = Σ_m p_m·δ(f − f_D,m)`（KDE 平滑）。
2. **原生谱先试**：
   - 近各向同性（宽角扩展、U 型）→ 直接 F64 `Classical/Jakes`，免拟合。
   - 近单窄峰 → 退化单高斯。
3. **双高斯拟合**：min `‖S_i − [w·N(μ_A,σ_A) + (1−w)·N(μ_B,σ_B)]‖`，得 `{μ_A,σ_A,μ_B,σ_B,w}` 与残差 `ρ_i`（EM 或 LSQ）。
4. **`ρ_i ≤ rho_thresh`** → 接受，输出 F64 `Gaussian` 双beam 参数（映射 `Beam A/B center shift + std + power ratio`）。
5. **`ρ_i > rho_thresh`（>2 模，拟合不动）→ 联合域分裂**：
   - 在 **(时延, 角度, 多普勒) 联合域**把 `S_i` 分成 `K≥2` 个模（GMM/峰检）。**注意：多普勒模 ↔ 角度组**（`f_D,n=(v/λ)cosθ_n`），分裂同时是角度分裂 → 各子簇 AoA/AoD 不同 → **下游探头 PAS 映射权重随之变**（见 §6.3，物理上正确）。
   - 每个分离模的安放：
     - **新建 tap**：若 tap 预算有余 **且** 与邻簇时延差 ≥ `delay_resolution`（否则落同一时延 bin 无法独立）。
     - **并入邻近 tap**：预算紧或时延不可分时。**前置校验**：接收簇吸收后**自身仍 ≤2 模**，否则只是搬家，禁止。
   - 各子簇重拟合（应已 ≤2 模 → 可拟合）。
6. **聚合**：`n_taps_after_split`、`ρ_max = max_i ρ_i`。

### 5.2 tap 预算是带约束优化（非贪心）
分裂消耗预算。目标：
```
min  Σ_i  P_i · ρ_i           （功率加权残差，强簇优先压低）
s.t. Σ_i  taps(i) ≤ tap_budget
     每子簇时延间隔 ≥ delay_resolution
```
即把有限 tap 预算优先花在主导 BER/吞吐的强簇，弱簇容忍更大残差。

### 5.3 标准先例（非 exotic）
3GPP TR 38.901 §7.5 step 11 本就把最强 2 簇**按时延**拆成 3 sub-cluster（偏置 `[0, 1.28, 2.56]·c_DS`，功率 10/6/4）。本算法是其**按多普勒/角度的自适应推广**（仅当 PSD 拟合不动时触发），落地有据。

---

## 6. 系统集成

### 6.1 判决时机与产物
- **时机**：场景入库 / TestCase 配置时（MPDB CDL 导出后），**一次性判决**。
- **产物**：`PathDecision { engine_mode, fit_result?, boundary_metrics, escalation_reason? }`。
  - `engine_mode ∈ { ASC_SYNTHESIS(=B-1), B2_PARAMETRIC_TDL(=B-2 新增), GCM_NATIVE(=escalation), EXTERNAL_ASC }`
  - `boundary_metrics` 落盘留痕：`f_D,max / f_D,crit / CIRs_total / FileSize_B1 / ρ_max / n_taps`（可审计、可复现判决）。

### 6.2 单一真值源 + fail-loud
- 判决结果进 **TestCase 元数据**，作为驱动全仪表层级的单一真值源（对齐 memory `project_testcase_driven_instrument_arch`）。
- **绝不静默兜底**：`ESCALATE` 必须显式暴露给操作员（GCM / 拆子路由 / 签字接受残差），不得默认回落某条路径。`gaussian_model_available==False` 等能力缺失同样 fail-loud。

### 6.3 下游分流
- **B-1**：ChannelEgine 现有 strict_pfs 子径求和 → per-link `.asc/.mat` → `.smu`（现状路径，已生产可用）。
- **B-2（新增）**：§5 输出 per-tap `{τ,P,Gaussian参数,fmax,K,AoA}` + 分裂后子簇 → `.tap/.rtc` → `.smu`；探头 PAS 映射须**消费分裂后的子簇角度**（§5.1 step 5 的角度分裂在此落地）。
- 两路最终都编译成 `.smu/.sim` 由 F64 加载（B-1 走 CIR 回放，B-2 走硬件衰落）。

### 6.4 engine_mode 落位
`api-service/app/services/channel_generation/base_generator.py::EngineMode` 现有 `GCM_NATIVE / ASC_SYNTHESIS / EXTERNAL_ASC`，**需新增 `B2_PARAMETRIC_TDL`**。判决函数是 engine_mode 的选择器。

---

## 7. 现场验证依赖（阈值标定，去现场前确认清单）

判决阈值依赖以下 F64 真机参数，**按优先级**：

1. **`gaussian_model_available` + `Gaussian` 双beam 参数写法**：现场 Channel Studio 版本/固件是否真有 `Gaussian` 谱、其 `Beam A/B center/std/power-ratio` 字段如何写入 `.tap/.smu`。**B-2 落地的头号前提**（决定 §5 算法有没有目标格式）。
2. **`f_upd_max`**：决定 `f_D,max,crit`。手册无，假设 10 kHz；若实测 ≥ 50 kHz，FR2 车载也能留 B-1（临界右移）。
3. **`tap_budget`**（24/48）、**`delay_resolution`**（5/10/20 ns）：决定 §5 分裂的预算与粒度。
4. **`rho_thresh`**：用吞吐/BER 灵敏度标定——多大 Doppler-PSD 误差不影响测量结论。
5. **`file_budget`**：运维侧定。
6. **逐通道独立模型 / 相关矩阵设单位阵**是否需额外 license（探头独立衰落落地，见 §6.3 与第三层探头设计）。

---

## 8. 验收（B-1 作为 B-2 的金标准）

1. **重叠区双跑对照**：选一个 **B-1、B-2 均可行**的场景，两路都生成，比对 QZ 处统计：**Doppler PSD / 空间相关 / 衰落包络 CDF**。B-2（双高斯近似）应在容差内贴合 B-1（精确）→ **据此标定 `rho_thresh`**。
2. **边界场景回归**：构造 `f_D,max` 跨临界、长路由超预算、>2 模需分裂等用例，断言判决落到预期 `engine_mode` 且 `boundary_metrics` 正确。
3. **fail-loud 用例**：`gaussian_model_available=False`、`ESCALATE` 路径必须显式报错/暴露，不静默兜底（对齐 memory `feedback_strict_gate_extend_bypass_toggle` 的门-旁路一致性思路）。

---

## 9. 开放问题（待 review 拍板）

1. **重叠区偏好**：B-1、B-2 均可行时默认 B-1（保真）。是否要给"长路由优先 B-2 省文件"的软阈值，还是一律 B-1？
2. **`requires_deterministic_phase` 我们用得上吗**：当前 MIMO OTA 主线是吞吐/BER（§10.1 判定只看 PSD → B-2 够）。确定性相位（波束跟踪/ISAC）是否在近期 scope 内？若否，Stage A 可暂记为"预留、默认 False"。
3. **`rho_thresh` 单值还是分场景**：FR1/FR2、不同测试例可能容忍度不同，是否要分级阈值。
4. **分裂的角度一致性归属**：§5 分裂产生的子簇角度变化，由 ChannelEgine 合成层统一承接，还是需要 MPDB 契约也表达"可分裂"语义？
5. **第三层（探头/PFS）耦合**：本设计聚焦 Doppler 维判决；探头独立衰落/PAS 合成（"另文"第三层）与 §5 分裂的角度联动，是否并入本文档下一版还是单列。

---

> 评审通过后，下一步：① `EngineMode` 增 `B2_PARAMETRIC_TDL` + 判决函数骨架（纯函数、可单测）；② §5 双高斯拟合 + 分裂算法原型 + 残差度量；③ 现场验证清单（§7）带去下次现场标定阈值。
