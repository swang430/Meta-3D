# RT → MPDB 多聚类 → 标注式 CDL → F64 信道注入完整设计（V1.0）

| 字段 | 值 |
|---|---|
| 性质 | 完整设计，供 review / 落地 |
| 版本 / 日期 | V1.0 / 2026-06-21 |
| 取代 | `B1-B2-path-decision-design_V0.1.md`（f_D,max 级联降级为本文附录 A） |
| 管线 | Lauraycs（RT 射线）→ ChannelEgine（MPDB 聚类 + 合成）→ MIMO-First（F64 驱动） |
| 上游依据 | `PROPSIM_F64_..._SCPI_V1.4_1.docx`（§7/§9/§10）；本轮 PROPSIM 手册深挖；NotebookLM 侧共识 |
| Roadmap | B-2 打通 / 信道注入主线（与 P2-11 GCM .smu 联动相邻），本文为设计件 |

---

## 0. TL;DR

1. **F64 没有任意自定义多普勒 PSD 参数口**（只 8 种闭式谱 + 双高斯 + Custom），任意 PSD 只能烘进 `.asc/.ir`（已手册证实）。
2. **突破**：降到 ≤24 抽头不可避免、且聚类由我们设计 —— 所以**按角度做 native 可表示聚类**，使每簇 Doppler 落在 F64 原生谱上 → **吞吐/一致性类测试 B-2 普及，绕开 custom PSD 墙、且免奈奎斯特覆盖全 f_D,max**。
3. **确定性相位类测试（ISAC / 波束跟踪）走 B-1 或 GCM**（B-2 是统计相位，结构性不适配），用**相位连续聚类**。
4. **MPDB 必须支持多样化聚类**：throughput→几何 native-fit 聚类；ISAC/波束跟踪→相位连续聚类。聚类必须是**时空跟踪**的（维持簇身份），否则毁掉 RT 的相位/空间连续性。
5. **核心交付物**：MPDB 聚类后的 **标注式 CDL 参数结构**（§5）—— 用 `doppler_repr` 区分联合体标注每簇的多普勒表示 + `cluster_id` 跨快照身份 + `clustering_meta` 声明聚类/路径/物理性，让下游确定性地分流到 B-1/B-2/GCM。

---

## 1. 既定结论（自洽前提，便于本文独立阅读）

| # | 结论 | 出处 |
|---|---|---|
| 1 | F64 参数化衰落只有闭式谱集；任意 PSD 仅能烘 `.asc/.ir` | User Reference Rev10.2 深挖 |
| 2 | **AS + AoA + 速度 = 多普勒展宽谱的参数输入**（宽度=AS，质心=f_D,max·cosφ，形状=固定扇）；ray 合成正为实现它 | 标准 SCM / 用户校正 |
| 3 | 当前格式只承载**标准扇形状**；非对称/多峰需另法 | cdl_schema.py + simulator.py:790 固定扇 |
| 4 | 聚类降维不可避免（≤24 抽头）且由我们设计 → 可选成"每簇 native 可表示" | 突破点 |
| 5 | B-2 = 统计实现（PSD 对、相位随机）；B-1/GCM = 确定性几何实现 | V1.4 §10.1 |
| 6 | 确定性相位测试 B-1 或 GCM 皆可（非只 GCM）；二者差在 license / 大质心(GCM ±1.5MHz vs B-1 ≤200kHz) / 谁算 | 本轮 Q1 |
| 7 | 逐快照独立聚类会毁连续性；必须**时空跟踪**聚类 | 本轮 Q2 |
| 8 | F64 ≤24/48 抽头/逻辑通道、1024 逻辑信道、相关阵可设单位阵（探头独立衰落可行） | 手册深挖 |

---

## 2. 总体架构

```
 Lauraycs RT                ChannelEgine                         MIMO-First / F64
 ┌──────────┐   子径(MPC)    ┌────────────────────────────┐  标注CDL  ┌──────────────┐
 │ 射线追踪  │ ─────────────▶│ MPDB 多聚类(可插拔)         │ ────────▶│ 路径分流      │
 │ 几何/角度 │  {τ,角,功率,  │  • geometric_native_fit(B2) │          │ • B2: .tap/   │
 │ /时延/功率│   相位}       │  • phase_continuous(B1/GCM) │          │   .rtc 硬件衰落│
 └──────────┘  按相关距离    │  • 时空跟踪(簇身份/生灭)     │          │ • B1: .asc/.mat│
                Δd_geo 采样   │ → 标注式 CDL(§5)            │          │   烘焙回放     │
                             │ → 合成分流(per doppler_repr) │          │ • GCM: .smu   │
                             └────────────────────────────┘          │ + 探头PFS(第三层)│
                                                                       └──────────────┘
```

**分层铁律**（对齐三仓架构）：
- **RT 端只产物理真值**（子径角度/时延/功率/相位），**不预判 F64 限制**。
- **ChannelEgine 端知道 F64 能力**，承担：聚类（核心 IP）+ native 谱映射 + 烘焙 + 标注。
- **MIMO-First/F64 端**按标注分流加载，不做信道决策。

---

## 3. MPDB 要求

### 3.1 必须携带 RT 子径（硬要求）
当前契约（`CustomCDLProfile`）每簇只有均值角 + 标量 AS + `num_rays` 计数，ChannelEgine 内部用**固定 38.901 扇**（`simulator.py:790` 的 `[0.0447,-0.0447,...]`）重建 —— **真实 RT 簇内角度结构在到达前已丢**。要做"按角度聚类使 native 可表示"或"相位连续聚类"，**ChannelEgine 必须拿到真实子径**：
```
subrays: List[{aoa_deg, aod_deg, zoa_deg, zod_deg, power_linear, phase_rad?}]   # 变长，RT native
```
> 目的不是喂 F64 custom PSD（F64 不收），而是**让聚类有原料**做出"让 F64 native 够用"的聪明降维 / 做确定性相位求和。

### 3.2 必须支持多样化聚类算法（可插拔）
MPDB 不是单一聚类，而是**按 `test_class` 选聚类策略**：

| test_class | 聚类算法 | 目的 |
|---|---|---|
| `throughput_psd` / `consistency` | **geometric_native_fit** | 每簇 native 可表示 → B-2 普及 |
| `isac_sensing` / `beam_tracking` | **phase_continuous** | 保确定性相位 + 连续性 → B-1/GCM |

两者共享**时空跟踪基底**（§4.3）。聚类策略是 MPDB 的可插拔组件（策略模式），输出统一的标注式 CDL（§5）。

---

## 4. 聚类算法

### 4.1 geometric_native_fit（B-2 路，核心 IP）
**目标函数**（带约束优化）：
```
min  Σ_i  P_i · ρ_i(native 拟合残差)   +   λ_t · Σ_i 时间不平滑度(i)
s.t. 每簇角度分布 native 可拟合(单峰→Gaussian / 宽角→Classical / 双峰→dual_gaussian)
     Σ_i taps(i) ≤ tap_budget(≤24)
     相邻快照簇身份一致(时空跟踪, §4.3)
     子径时延间隔 ≥ delay_resolution
```
- native 谱映射：`f_d_centroid = f_D,max·cosφ`、`f_d_max(展宽半宽) ∝ f_D,max·sinφ·AS`；单峰→`gaussian{std}`、宽角各向同性→`classical`、轻度双峰→`dual_gaussian{beamA,beamB,power_ratio}`。
- **>2 峰**：在(时延,角度,多普勒)联合域分裂为 ≤2 模子簇（新 tap 或并邻簇，接收簇须仍 ≤2 模），分裂血缘记 `parent_cluster_id`。分裂同时是角度分裂 → 子簇新均值角喂下游探头 PAS。
- 残差超阈且分裂/预算解不开 → 标 `target_path=B1_baked` 退路（§6）。

### 4.2 phase_continuous（B-1/GCM 路）
- **不要求 native 可表示**（B-1 烘什么形状都行 / GCM 内部求和），但**要求确定性相位 + 强连续性**。
- 聚类目标：时间连续 + ≤24 抽头 + **保留子径确定性初相** `phase_rad`，使 `doppler_repr=subray_sum`，下游确定性求和（B-1 烘 `.asc`，或 GCM 内部求和）。
- 大质心拆出走硬件频偏（B-1 ≤200kHz / GCM Advanced Doppler ±1.5MHz）。

### 4.3 共同的时空跟踪基底（连续性命根，两路都用）
逐快照独立聚类会让簇身份跳变 → F64 快照间插值在不匹配簇间插 → 毁相位/空间连续性。故两路都建立在**簇跟踪**上：
- 沿轨迹关联 `cluster_id`（C_i(k) ↔ C_i(k+1)），参数平滑演化。
- 生灭（birth/death）用功率渐变标注（`power_ramp`），不跳变。
- 参考动态 GBSM：38.901 §7.6.3 spatial consistency / COST 2100 visibility region。
- **两层连续性**：统计连续（簇均值轨迹 + AS/PSD 演化）两路都保；确定性相位连续仅 phase_continuous + B-1/GCM 保（B-2 统计相位本性给不了）。

---

## 5. ★ 标注式 CDL 参数结构（核心交付物）

MPDB 聚类后输出的 CDL，用三层结构 + `doppler_repr` 区分联合体**标注每簇该如何被下游处理**。Pydantic v2 风格（扩展现 `CustomCDLProfile`，向后兼容）。

### 5.1 顶层：AnnotatedCDLProfile
```python
class AnnotatedCDLProfile(BaseModel):
    # ── 全局物理（兼容现 CustomCDLProfile）──
    center_frequency_hz: float
    pathloss_db: float
    is_los: bool
    k_factor_db: float | None = None

    # ── ★ 聚类/路径标注（新）──
    clustering_meta: ClusteringMeta
    trajectory_meta: TrajectoryMeta | None = None     # None = 单快照(静态)

    # ── 快照序列：len==1 即静态；兼容旧"单 profile"语义 ──
    snapshots: list[CDLSnapshot]                        # 至少 1


class ClusteringMeta(BaseModel):
    algorithm:   Literal['geometric_native_fit', 'phase_continuous', 'raw_passthrough']
    target_path: Literal['B2_parametric', 'B1_baked', 'GCM_native']
    test_class:  Literal['throughput_psd', 'consistency', 'isac_sensing', 'beam_tracking']
    physicality: Literal['rt_physical', 'standard_fan', 'mixed']   # §10.1 物理性来源
    f64_profile_ref: str                  # 用了哪份 F64 能力档(tap_budget/f_upd_max/rho_thresh)
    tap_budget_used: int
    max_native_fit_residual: float | None = None        # B-2 全场景最大残差(验收门)
    notes: str | None = None


class TrajectoryMeta(BaseModel):
    n_snapshots: int
    skeleton_rate_hz: float               # 几何骨架率(~100Hz)
    delta_d_geo_m: float                  # 几何重算间隔
    route_len_m: float
    cir_update_rate_hz: float | None = None   # B-1 的 f_upd；B-2 = None/骨架率


class CDLSnapshot(BaseModel):
    index: int
    time_s: float | None = None
    position_m: tuple[float, float, float] | None = None
    ue_velocity_mps: tuple[float, float, float]         # 该快照速度矢量(方向随轨迹变)
    clusters: list[AnnotatedCluster]
```

### 5.2 簇：AnnotatedCluster
```python
class AnnotatedCluster(BaseModel):
    # ── 身份与跟踪(★ 连续性核心)──
    cluster_id: int                       # 跨快照稳定身份
    parent_cluster_id: int | None = None  # 由分裂而来则指父簇
    birth_index: int | None = None        # 生命周期(动态)
    death_index: int | None = None
    power_ramp: Literal['stable', 'birth', 'death'] = 'stable'

    # ── 标准几何/功率(与现 CDLClusterSpec 兼容)──
    delay_s: float
    power_linear: float
    aoa_deg: float; aod_deg: float; zoa_deg: float = 90.0; zod_deg: float = 90.0
    as_aoa_deg: float = 0.0; as_aod_deg: float = 0.0
    as_zoa_deg: float = 0.0; as_zod_deg: float = 0.0
    xpr_db: float | None = None
    initial_phases_rad: list[float] | None = None        # [4]

    # ── ★ 多普勒表示标注(区分联合体)──
    doppler_repr: DopplerNative | DopplerDualGaussian | DopplerBaked | DopplerSubraySum

    # ── 物理性(per-cluster，可与顶层不同)──
    physicality: Literal['rt_physical', 'standard_fan'] = 'rt_physical'

    # ── 可选子径(baked / subray_sum / phase_continuous 时携带)──
    subrays: list[SubRay] | None = None


class SubRay(BaseModel):
    aoa_deg: float; aod_deg: float; zoa_deg: float; zod_deg: float
    power_linear: float
    phase_rad: float | None = None        # 确定性初相(phase_continuous 必需)
```

### 5.3 DopplerRepr 区分联合体（`kind` 判别）
```python
class DopplerNative(BaseModel):           # B-2，映射到 F64 原生谱
    kind: Literal['native'] = 'native'
    shape: Literal['classical', 'gaussian', 'rounded', 'flat', 'pure_doppler', 'rice']
    f_d_centroid_hz: float                # = f_D,max·cosφ
    f_d_max_hz: float                     # 该簇展宽半宽(∝ AS·sinφ)
    shape_params: dict | None = None      # gaussian:{std_hz}; rice:{k_db}; ...
    native_fit_residual: float            # 拟合残差 ρ(验收用)

class DopplerDualGaussian(BaseModel):     # B-2，双高斯逼近(F64 Gaussian 双beam)
    kind: Literal['dual_gaussian'] = 'dual_gaussian'
    beam_a: dict                          # {center_shift_hz, std_hz}
    beam_b: dict                          # {center_shift_hz, std_hz}
    power_ratio_db: float
    native_fit_residual: float

class DopplerBaked(BaseModel):            # B-1，多普勒烘进 CIR
    kind: Literal['baked'] = 'baked'
    f_d_centroid_hz: float = 0.0          # 大质心若拆出走硬件频偏
    cir_ref: str | None = None            # 指向 .asc/.mat/.ir(可后填)
    # 形状不参数化，靠 subrays/CIR 序列承载

class DopplerSubraySum(BaseModel):        # B-1/GCM，确定性子径求和
    kind: Literal['subray_sum'] = 'subray_sum'
    deterministic_phase: Literal[True] = True
    f_d_centroid_hz: float = 0.0
    # 完全靠 subrays[] 的确定性相位，downstream 求和
```

### 5.4 消费契约与一致性校验（fail-loud）
下游**必须按标注处理**，且 MPDB 输出时做一致性自检（对齐 TestCase 单一真值源 + fail-loud）：
- `target_path == B2_parametric` ⟹ 所有簇 `doppler_repr.kind ∈ {native, dual_gaussian}`；否则 422。
- `target_path ∈ {B1_baked, GCM_native}` ⟹ 所有簇 `kind ∈ {baked, subray_sum}`；`subray_sum` 必须每子径有 `phase_rad`。
- `algorithm == phase_continuous` ⟹ `target_path != B2_parametric`（确定性相位不能交统计衰落）。
- 动态场景 ⟹ 每个 `cluster_id` 在相邻 in-life 快照间存在（连续性可校验）；`birth/death` 处 `power_ramp != 'stable'`。
- `physicality == 'standard_fan'` 但 `algorithm == 'geometric_native_fit'` ⟹ warn（你在对 generic 数据做 native 拟合，无 RT 增益）。

### 5.5 示例（动态、throughput、B-2、含一次分裂）
```jsonc
{
  "center_frequency_hz": 3.5e9, "pathloss_db": 98.2, "is_los": false,
  "clustering_meta": {
    "algorithm": "geometric_native_fit", "target_path": "B2_parametric",
    "test_class": "throughput_psd", "physicality": "rt_physical",
    "f64_profile_ref": "F64_CAICT_2026Q2", "tap_budget_used": 18,
    "max_native_fit_residual": 0.043
  },
  "trajectory_meta": {
    "n_snapshots": 1200, "skeleton_rate_hz": 100, "delta_d_geo_m": 1.11, "route_len_m": 1332,
    "cir_update_rate_hz": null
  },
  "snapshots": [
    {
      "index": 0, "time_s": 0.0, "ue_velocity_mps": [33.3, 0, 0],
      "clusters": [
        {
          "cluster_id": 1, "delay_s": 0.0, "power_linear": 0.51,
          "aoa_deg": 12.0, "aod_deg": -30.0, "as_aoa_deg": 8.0,
          "doppler_repr": {
            "kind": "native", "shape": "gaussian",
            "f_d_centroid_hz": 388.9, "f_d_max_hz": 54.0,
            "shape_params": {"std_hz": 41.0}, "native_fit_residual": 0.021
          },
          "physicality": "rt_physical"
        },
        {
          "cluster_id": 7, "parent_cluster_id": 3,        // 由簇3分裂而来(>2峰)
          "delay_s": 2.1e-7, "power_linear": 0.18,
          "aoa_deg": 95.0, "aod_deg": 10.0, "as_aoa_deg": 5.0,
          "doppler_repr": {
            "kind": "dual_gaussian",
            "beam_a": {"center_shift_hz": -120.0, "std_hz": 30.0},
            "beam_b": {"center_shift_hz": 60.0, "std_hz": 25.0},
            "power_ratio_db": 3.5, "native_fit_residual": 0.061
          },
          "physicality": "rt_physical"
        }
      ]
    }
    /* … 1199 个后续快照，cluster_id 1/7 平滑演化 … */
  ]
}
```

> 同结构也表达 ISAC 路：`clustering_meta.target_path="B1_baked"`、每簇 `doppler_repr.kind="subray_sum"` + 完整 `subrays[]` 带 `phase_rad`。**一个 schema 标注两路。**

---

## 6. 路径判决（突破后大幅简化：test_class 驱动）

```python
def select_path_and_clustering(test_class, scenario, f64_profile):
    if test_class in ('isac_sensing', 'beam_tracking'):
        # 确定性相位：B-1 或 GCM(本轮 Q1 纠正)。
        # 大质心(>200kHz) / FR2 高速区 B-1 不可行(奈奎斯特 + 亚毫米地图，§9.5)，
        # 该区必须 GCM；若无 GCM license 则 fail-loud ESCALATE，
        # 【绝不静默回落 B1_baked】(否则会选到不可行路径 — Codex P2 #165)。
        gcm_required = need_large_centroid(scenario) or is_fr2_high_speed(scenario)
        if gcm_required:
            return ('GCM_native' if f64_profile.has_gcm else 'ESCALATE'), 'phase_continuous'
        return 'B1_baked', 'phase_continuous'        # 低 f_D,max 确定性 → B-1 可行

    # throughput/consistency：B-2 普及
    fit = geometric_native_fit(scenario, f64_profile)              # §4.1
    if fit.ok(f64_profile.rho_thresh, f64_profile.tap_budget):
        return 'B2_parametric', 'geometric_native_fit'
    # native-vs-连续冲突区 → B-1 退路(本轮 Q2)
    return 'B1_baked', 'phase_continuous'
```

> `f_D,max` / 文件经济（原 V0.1 主边界）**降级为 B-1 被选中后的可行性校验**（高 f_D,max 时 B-1 烘不动 → 若仍落 B-1 则报 ESCALATE_GCM），不再是主判决。详见附录 A。

---

## 7. ChannelEgine 合成分流（per `doppler_repr`）

| `doppler_repr.kind` | 合成动作 | 产物 |
|---|---|---|
| `native` | 映射到 F64 原生谱参数（shape + 质心 + 展宽） | per-tap 参数行 → `.tap/.tdlx` |
| `dual_gaussian` | 写 F64 `Gaussian` 双beam 参数 | per-tap → `.tap/.tdlx` |
| `baked` | 子径求和烘 CIR（现 strict_pfs 路径） | `.asc/.mat/.ir` |
| `subray_sum` | 确定性子径相干求和（保 `phase_rad`） | `.asc/.mat`（B-1）/ 交 GCM |

- B-2 多位置 → 打包 `.rtc`，几何骨架率切换 environment。
- 两路最终编译 `.smu/.sim` 由 F64 加载。
- `EngineMode` 新增 `B2_PARAMETRIC_TDL`（现 `base_generator.py` 仅 GCM_NATIVE/ASC_SYNTHESIS/EXTERNAL_ASC）。

---

## 8. F64 落地 + 第三层探头 PFS 接口

- **B-2**：`.tap/.tdlx` per-tap {τ,P,native谱,fmax,K,AoA} + `.rtc` 容器；硬件实时衰落。
- **B-1**：`.asc/.mat` CIR 回放 + 运行时频偏承载大质心。
- **GCM**：`.smu` 直出（需 license）。
- **第三层探头独立衰落（strict_pfs）**：每探头 = 一个 logical channel（F64 ≤1024）+ **相关矩阵设单位阵**（手册证实可设独立）→ F64 逐探头独立生成衰落，几何权重 W_base 作 per-channel 静态复权重。**本文聚焦 Doppler/聚类轴；探头 PAS 映射消费 §5 分裂后的子簇角度**（angle↔Doppler 联合分裂的下游）。

### 8.1 注入拓扑边界与校准注入契约（本轮 OTA / conducted 独立条目）

> 2026-06-21 用户决策（开 B-1 烘焙前确认）：本轮 B-1/B-2 软件补全**只做 OTA**，conducted 列为独立条目。下方固化边界，免后续烘焙器漏维度。

**本轮注入边界 = OTA**。现有 `channel_generation/` 全部 5 策略（ASC / EXTERNAL_ASC / GCM / B2 / base）+ ChannelEgine 导出层一律 OTA：信道按物理探头展开（per-(Tx, Probe) logical channel）+ 施加 OTA 校准 + PAS 旋转对齐探头。B-1/B-2 标注式烘焙本轮**沿用 OTA 拓扑**，与现有栈一致。

**校准注入契约（OTA）**：B-1（`.asc`）/ B-2（`.tap`）烘焙在导出边界消费 `CalibrationConfig`（per-probe-port：`cable_loss_db` + `probe_gain_dbi` + `cable_phase_deg` → `get_correction_factor` 复预失真 `1/H_sys`），施加在 per-(Tx, Probe) logical channel 上（与 `PropsimASCIIExporter.apply_calibration` 同源）。**烘焙器必须显式接收校准 + 测试断言「校准已施加」，不得当黑盒默认「复用即自动对」。** UL 方向不施加（沿用现有 `direction != "ul"`）。

**conducted（传导）= 独立 roadmap 条目，本轮不实现**。语义与 OTA 根本不同：DUT 天线直连仪器（**不展开 32 探头**，per-(Tx-antenna, Rx-antenna)）+ **线缆校准**（无 `probe_gain_dbi` / 无 PAS 旋转）+ 文件为天线对而非探头对。这是横切**全部**引擎（ASC/GCM/B2/B1）的维度，现有注入栈 0 实现（仅 `TestMode.CONDUCTED` / `TopologyType.CONDUCTED` 在业务模型层声明）。单独设计（拓扑分流 + 线缆校准建模）+ 单独 PR；本轮烘焙器**接口预留**（拓扑参数默认 OTA，conducted 分支后补）。

---

## 9. 现场验证依赖（按优先级）

1. **`gaussian_model_available` + 写法**：现场 Channel Studio 是否有 `Gaussian` 双beam 谱、字段如何写入 `.tap/.smu`（**B-2 头号前提**）。
2. **`f_upd_max`**：决 B-1 临界（仅影响 B-1 退路与确定性低频路）；手册无，假设 10kHz。
3. **`tap_budget`(24/48) / `delay_resolution`(5/10/20ns)**：决聚类预算/分裂粒度。
4. **`rho_thresh`**：用吞吐/BER 灵敏度标定（多大 native 残差不影响结论）。
5. **`.rtc` 环境切换抖动**：~100Hz 切换瞬态是否污染 OFDM 符号（连续性硬件侧）。
6. **逐探头独立 logical channel + 单位阵相关**是否需额外 license。
7. **大质心**：B-1 运行时频偏上限（≤200kHz?）/ GCM Advanced Doppler ±1.5MHz 确认。

---

## 10. 验收

1. **B-1 金标准对照 B-2**：重叠场景两路都生成，比对 QZ 处 Doppler PSD / 空间相关 / 衰落 CDF → 标定 `rho_thresh`。
2. **连续性用例**：动态场景断言 `cluster_id` 跨快照存在、参数平滑、F64 插值无跳变；`.rtc` 切换瞬态实测。
3. **确定性相位用例**：ISAC/波束跟踪场景走 B-1/GCM，验证相位↔几何可反演。
4. **fail-loud 用例**：§5.4 一致性校验、`ESCALATE`、能力缺失必须显式报错不静默兜底。

---

## 11. 开放问题

1. **聚类时间正则权重 `λ_t`**：native 可表示 vs 时间连续的权衡系数如何定/是否分场景。
2. **`physicality` 混合场景**：一个场景内强簇 rt_physical、弱簇退 standard_fan 是否允许（`mixed`）。
3. **第三层探头 PFS** 与 §5 分裂角度联动：本文给了接口（§8），完整探头侧设计是否单列另文。
4. **MPDB schema 落库**：扩 `CustomCDLProfile` → `AnnotatedCDLProfile` 的迁移与契约同步（client/微服务/openapi 四步）。
5. **ISAC 在 OTA 的可行性**：探头式 PAS 合成能否支撑单/双站感知几何 —— 超出本文，需另评。

---

## 附录 A：f_D,max 级联（原 V0.1 主体，降级保留）

突破前的判决以 `f_D,max = v·f_c/c` 为主边界、`f_D,max,crit = f_upd,max/(2·SD)` 为阈。突破后：B-2 免奈奎斯特覆盖全 f_D,max，该级联**仅在 B-1 被选中（确定性相位 / native 冲突退路）时**作可行性校验：
```
B-1 选中后:  f_D,max > f_upd,max/(2·SD)  →  B-1 烘不动  →  ESCALATE_GCM
            文件 CIRs_total=2·SD·D/λ 超预算  →  ESCALATE_GCM
```

## 附录 B：与现有代码的接口
- `ChannelEgine/mimo_ota_simulator/cdl_schema.py`：`CustomCDLProfile/CDLClusterSpec` → 扩为 `AnnotatedCDLProfile/AnnotatedCluster`（向后兼容：单快照 + 全 native + 默认标注 = 现行为）。
- `ChannelEgine` 新增聚类模块（策略模式：geometric_native_fit / phase_continuous + 时空跟踪基底）。
- `api-service/.../channel_engine_client.py`：`CDLCluster` 镜像新字段。
- `api-service/.../base_generator.py`：`EngineMode` 增 `B2_PARAMETRIC_TDL`。
- `api-service/app/hal/propsim_f64.py`：B-2 `.tap/.rtc` 加载路径（现有 `.rtc`/EXTERNAL_WAVEFORM 原语可复用）。
