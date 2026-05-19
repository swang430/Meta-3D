# Commissioning → ChannelEgine 数据流 (P1-7 收口快照)

**Date**: 2026-05-19
**Status**: live, post PR #59 (P1-7) merge
**Audience**: 新接手 MIMO-First / ChannelEgine 集成的工程师 + 将来扩 PWS / 非标暗室
的设计参考

---

## 为什么有这份文档

P1-7 (PR #59) 之前, `mimo_first_asc` commissioning 路径有 4 段相互独立但有
契约的代码:

1. ChannelEgine library (mimo_ota_simulator + channel_builders) — 跨 repo
2. `channel-engine-service` 微服务 (端口 8001) — MIMO-First 内, 包装 ChannelEgine
3. `ChannelEngineClient` (api-service 内的 HTTP 客户端)
4. `ExternalWaveformStrategy.generate_and_load` (commissioning 调用站点)

P0-7 (#56) 修了 1+2+3 的 API mismatch + 端到端 e2e gated test 跑通。但 4
[`asc_strategy.py:62-77`](../../api-service/app/services/channel_generation/asc_strategy.py#L62)
仍然 hardcode `CDLCluster(delay_s=0.0, power_relative_linear=1.0)  # Mock`,
即使下游全打通了, **operator 在 GUI 选 "UMa NLOS CDL-C" 实际打到 ChannelEgine
的还是 1 个 placeholder 簇**, 不是 38.901 多径。

P1-7 (#59) 拆掉这个 mock cluster, 走 `input_mode='standard'` 让 ChannelEgine
内部 `Standard3GPPBuilder` 生成 24-cluster 真 38.901 (smoke 见 zip 86 KB →
725 KB 8× 跳)。这条 wire-up 第一次形成完整闭环, 这份文档把全景画下来 + 标出
几个 surprising 点 + ring-only silent constraint 留档 (→ P2-7)。

---

## 全景图 — 跨 repo 边界

```
┌─────────────────────────────────────────────────────────────────────┐
│  MIMO-First repo                                                    │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  api-service  (端口 8000, GUI 后端)                            │   │
│  │                                                              │   │
│  │  operator GUI ──→ TestStep / cdl_model_data dict ──→         │   │
│  │      ExternalWaveformStrategy.generate_and_load              │   │
│  │           ↓                                                   │   │
│  │      ChannelEngineClient.synthesize_hardware_pipeline         │   │
│  │      ↑           ↓                                            │   │
│  │      │  DB 查询 (PostgreSQL):                                  │   │
│  │      │   - ChamberConfiguration (按 chamber_id)               │   │
│  │      │   - ProbePathLossCalibration (按 chamber + freq, VALID)│   │
│  │      │   - ProbePhaseCalibration (按 chamber + freq)          │   │
│  │      │   - Probe.position{az,el} — 仅 PAS rotation, 不进 payload│ │
│  │      ↓                                                        │   │
│  │      _build_payload()  →  HTTP POST 到 :8001                  │   │
│  └────────────────────────────────────│─────────────────────────┘   │
│                                       ↓                             │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  channel-engine-service  (端口 8001, 微服务)                   │   │
│  │                                                              │   │
│  │  FastAPI POST /api/v1/synthesize_hardware_pipeline           │   │
│  │      ↓                                                        │   │
│  │  HardwarePipelineRequest (Pydantic schema)                   │   │
│  │      ↓                                                        │   │
│  │  _build_target_channel_config — payload → CE 配置对象          │   │
│  │      ↓ (input_mode='standard' OR 'custom')                   │   │
│  │  import ChannelEgine (作为 Python library 依赖)              │   │
│  └────────────────────────────────────│─────────────────────────┘   │
└────────────────────────────────────────│─────────────────────────────┘
                                         │
                          (Python import boundary, in-process)
                                         │
┌────────────────────────────────────────│─────────────────────────────┐
│  ChannelEgine repo  (独立项目)          ↓                             │
│                                                                       │
│  MIMO_OTA_Simulator (无状态计算 library):                              │
│   - Standard3GPPBuilder      ← input_mode='standard' 走这条           │
│   - CustomCDLBuilder         ← input_mode='custom' 走这条             │
│   - ChannelSimulator         ← 内部 strict_pfs / TR 38.901 generator  │
│   - PropsimASCIIExporter     ← 输出 .asc ZIP base64                   │
│                                                                       │
│  没有 PostgreSQL, 没有网络, 没有 chamber DB. 所有输入参数通过           │
│  TargetChannelConfig + ChamberConfig + AntennaArrayConfig 三个         │
│  Pydantic-like 类的函数签名传入. 跟 MIMO-First 解耦.                   │
└───────────────────────────────────────────────────────────────────────┘

  Result: asc.zip base64 → HTTP 200 → MIMO-First 解压 → HAL upload → F64
```

**关键边界**: ChannelEgine 是**纯计算 library**, 无状态/无 DB/无网络。MIMO-First
所有需要 ChannelEgine 知道的东西**必须显式打包进 HTTP payload**, ChannelEgine
不会"穿越"到 MIMO-First 的 DB 拿数据。这是个干净边界, 跨 repo 时不会有"咦它
怎么读到这个"的混乱。

---

## HTTP payload 详细 schema (P1-7 之后)

```jsonc
{
  // 暗室几何元数据 — ChannelEgine 用这个生成 probe ring 布局
  "chamber_config": {
    "num_probes": 8,
    "radius_m": 2.0,
    "dual_polarized": true,
    "distribution": "ring"          // ★ hardcoded, 见下面 silent constraint
  },

  // 物理链路逐 port 损耗 + 增益 + 相位补偿
  "calibration_data": {
    "entries": [
      {
        "port_id": 1,                // probe_id × 2 + (V=1 / H=2)
        "cable_loss_db": 5.7,        // 来自 ProbePathLossCalibration 或 fallback
        "cable_phase_deg": 0.0,      // ★ injected 但 strict_pfs 不消费 (PWS 用)
        "probe_gain_dbi": 8.0
      }
      // ...每 probe × pol 一个 entry, 共 num_probes × 2 个 (双极化 chamber)
    ]
  },

  // 仿真参数 (频率 / 功率目标 / 天线阵 / 速度 / 合成方法)
  "simulation_rules": {
    "center_frequency_hz": 3.5e9,
    "target_tx_power_dbm": 0.0,
    "target_rsrp_dbm": -85.0,
    "target_snr_db": 20.0,
    "tx_antenna": {                  // BS-side antenna array (gNB)
      "array_type": "URA",
      "num_rows": 2,
      "num_cols": 4,
      "spacing_h": 0.5,
      "spacing_v": 0.5,
      "polarization": "V"
    },
    "rx_antenna": { /* UE-side */ },
    "ue_velocity_kph": 15.0,
    "ue_velocity_mps": null,         // 优先用; null 时从 kph 派生
    "synthesis_method": "strict_pfs" // P0-7 透传, 走 ChannelEgine Phase 1+ strict PFS
  },

  // CDL 模型描述
  "cdl_model_data": {
    "model_name": "UMa NLOS CDL-C",  // operator-facing 字符串, 不消费
    "pathloss_db": 100.0,
    "is_los": false,                 // 从 parse_cdl_model_name 派生
    "k_factor_db": null,             // null → ChannelEgine TR 38.901 §7.5.6 默认
    "clusters": null                 // ★ standard mode 必须 null; custom mode 带显式簇
  },

  // P1-7 加的 dispatch 字段
  "input_mode": "standard",          // OR "custom"

  // P1-7 加的 standard-only sub-model
  "standard_3gpp": {
    "scenario_name": "UMa",          // canonical, alias 已 resolved
    "cluster_model_name": "CDL-C",
    "force_condition": "NLOS",       // "LOS" / "NLOS" / "auto"
    "bs_position": [0.0, 0.0, 25.0], // TR 38.901 §7.2 典型几何, operator 可覆盖
    "ue_position": [50.0, 0.0, 1.5],
    "random_seed": null              // 可重现仿真用
  }
}
```

---

## 四个 surprising 点 — 不是 bug, 但容易踩坑

### 1. 链路损耗是 **static folding**, 不是 dynamic compensation

`_query_calibration_entries` 没校准数据时的 fallback 公式:

```python
effective_loss = chamber.typical_cable_loss_db
if chamber.has_pa and chamber.pa_gain_db:
    effective_loss -= chamber.pa_gain_db      # PA 增益当成负损耗
if chamber.has_duplexer and chamber.duplexer_insertion_loss_db:
    effective_loss += chamber.duplexer_insertion_loss_db
```

→ PA / duplexer / cable 三者**折成一个标量** `cable_loss_db` 进 payload。
ChannelEgine 看不到 `has_pa` / `has_duplexer` 这些原始字段, 看的只是一个数。

**坑**: 如果 PA 增益跟频率有关 (大部分宽带 PA 跨段有 1-3 dB ripple), 单一
`pa_gain_db` 标量是失真的。**真校准** (跑过 `ProbePathLossCalibration`) 一旦
灌好就盖掉这个 fallback, 现场跑过校准后影响不大; 但**没校准的 smoke** 是带
这个误差的, 不是高保真的。

### 2. PFS 模式下 phase calibration **injected but unused**

`_query_phase_compensation` 真去查 DB 并塞进每个 entry 的 `cable_phase_deg`,
[`phase_compensation_map`](../../api-service/app/services/channel_engine_client.py)
注入逻辑都 wired up。但:

- 当前生产路径是 strict PFS (Phase 1+, see [PFS phase-immunity 推导](../features/calibration/pfs-phase-immunity.md))
- strict PFS 对**绝对相位免疫**, `cable_phase_deg` 在 PFS 路径里被 ChannelEgine
  内部直接丢弃
- 基建保留是为将来 PWS (Phase Wavefront Synthesis, 强 phase-coherent)

→ 当前是 **noop with audit trail**: 你能在 log 里看到 "Phase calibration injected
for N/M ports", 但 .asc 输出跟 phase cal 没关系。**别误以为 phase cal 接入了
就等于在用**。

### 3. Commissioning **precheck 不拦未校准 chamber** (silent failure mode #2)

> **修订 2026-05-19** (Codex P2 on PR #60 commit 81f6923): 本节初版描述
> "Cert 没灌好 → precheck fail-loud" — **错的**。实际行为见下。

[`PrecheckExecutor`](../../api-service/app/services/mimo_ota/executors/precheck.py)
第 236 行计算:

```python
overall_pass = critical_online and qz_pass and ue_cap_pass
```

`overall_pass` 只检查三件事:
1. `critical_online` — `baseStation` + `channelEmulator` HAL driver 在线
2. `qz_pass` — quiet zone ripple ≤ `max_quiet_zone_ripple_db` threshold
3. `ue_cap_pass` — UE max_dl_layers ≥ `config.mimo_layers`

**校准状态完全没进 `overall_pass`**:

- `path_loss_calibration_valid = False` (没找到 VALID 的 ProbePathLossCalibration)
  → 只 append warning `"Phase 3 will fall back to default cable loss"`,
  不阻断 (precheck.py:198-202)
- `calibration_certificate is None` → 只 warning, 不阻断 (precheck.py:175-176)
- `cal_cert.overall_pass = False` (cert 存在但 cert 自己标 not pass) → record 进
  `result_payload` 但**不影响 precheck 的 overall_pass** (precheck.py:170-173)

**实际后果**: 操作员可以从零开始 (没建过任何 cal cert / 没跑过路损校准) 直接
跑 commissioning, precheck phase 会 PASS, 然后:

- measure phase 调 `ChannelEngineClient` → `_query_calibration_entries`
- 没找到 `ProbePathLossCalibration` → fallback 公式:
  `effective_loss = typical_cable_loss_db + duplexer - pa_gain` (见上面 surprising #1)
- 拿这个标量当所有 port 的 cable_loss_db → 生成 .asc → 上传到 F64 → 跑测试

→ commissioning 实际跑出来的 KPI 是基于 `ChamberConfiguration` 表里的**典型值**,
不是这个 chamber 真实测过的路损。在 lab 内 ring 8-probe 这种"配置参数贴近
典型"的场景, 数值上可能差不多 (1-3 dB), 但**这不是设计意图**, 设计意图是
operator 必须先跑路损校准 (P0-3 输出) 才能跑 commissioning。

**当前规避**: GUI commissioning workflow 实际是"先 calibration tab 后 commission",
operator 主观上不太会忘 — 但**没有 code-level 安全 net**。

**该修**: precheck 至少应该把 `path_loss_calibration_valid == False` 或
`cal_cert is None` 升到 `overall_pass = False` (或加新的 strict mode flag),
让 commissioning fail-loud 拒绝在未校准 chamber 上跑。Triage in
[`roadmap-first-call.md`](../roadmap-first-call.md) "Discovered during P1-7
catch-up review" backlog 区。

### 4. `BaseChannelGenerator.calibration_entries` 是 **dead weight** (constructor 漂移)

```python
class BaseChannelGenerator(ABC):
    def __init__(
        self,
        emulator: ChannelEmulatorDriver,
        chamber_config: Any,
        calibration_entries: List[Dict],  # ← 收到这个
    ):
        ...
        self.calibration_entries = calibration_entries  # ← 存在 self 上
```

`ExternalWaveformStrategy.generate_and_load` **完全没读 `self.calibration_entries`**。
真正的 calibration entries 是 `ChannelEngineClient` 自己从 DB 重查的。

→ 不会出错 (单一真源在 DB), 但 future 工程师改 commissioning 流程时会困惑
"这个 cal_entries 参数到底有没有用"。**当前是 redundant indirection, 不是 bug**。
要清理的话 → P3-level cleanup, 不阻塞任何东西。

---

## ★ ring-only silent constraint (→ P2-7)

**当前 schema 写死**:

```python
"chamber_config": {
    "num_probes": 8,
    "radius_m": 2.0,
    "dual_polarized": True,
    "distribution": "ring",   # ← hardcoded, 没有别的选项
}
```

- probe 物理 azimuth/elevation 角度 **不进 payload**
- ChannelEgine 内部按 `(port_id - 1) × 360° / num_probes` 推 ring 等间距假设
  (3GPP TR 37.977 §6.1 标准布局)
- MIMO-First DB 里 `Probe` 表实际存了 `position: {azimuth, elevation}` (PAS
  rotation 代码就读这个), 但**没传给 ChannelEgine**

**silent failure mode**: 操作员配一个非标 chamber (sparse / sector / dual-ring),
MIMO-First DB 不会拒, ChannelEgine 算 .asc 时 silently 当成 ring 等间距,
物理几何跟 .asc 反映的角度不符, **没人会报错**。

**当前不阻塞**: lab 唯一在用的就是 ring 8-probe, 跟假设一致。

**何时显化**:
- PWS 工程开始 (PWS 用 sector geometry)
- 非标暗室 (sparse layout 省 probe, dual-ring 增强 elevation)

**跟踪**: P2-7 "非 ring 暗室 probe 几何支持 (cross-repo)" — 见
[`roadmap-first-call.md`](../roadmap-first-call.md)。主要工作在 ChannelEgine
(PAS / cluster→port 映射要消费真实角度, 不能再按 `(port-1)×360°/N` 算),
MIMO-First 这边是 schema + DB plumbing 的小工作。

---

## 跟 cal cert 工作链的衔接

> **修订 2026-05-19** (Codex P2 on PR #60 commit 81f6923): 本节初版宣称
> "precheck gate + lazy DB lookup + silent fallback 三层保护", **错的** —
> precheck 实际不拦 cal-missing (见 surprising #3)。

P0-3 (path-loss cal cert) + P1-5 (phase cal cert) 在搭的
`ProbePathLossCalibration` + `ProbePhaseCalibration` 链路, **接进生产路径但
缺安全 net**:

1. operator 跑 commissioning → precheck phase
   ([`precheck.py:165-202`](../../api-service/app/services/mimo_ota/executors/precheck.py#L165-L202))
   读 `ProbePathLossCalibration` + `calibration_certificate`, 写进
   `result_payload` 让下游 audit 可见, 但**任何 cal 缺失只 append warning,
   不拦 `overall_pass`** (详见 surprising #3)
2. precheck 通过 → measure phase → asc_strategy → ChannelEngineClient
3. ChannelEngineClient `_query_calibration_entries` 查最新 VALID 的
   `ProbePathLossCalibration`, **没找到则 silently fallback 到**
   `typical_cable_loss_db + duplexer - pa_gain` 公式 (见 surprising #1)
4. fallback 标量进 HTTP payload `calibration_data.entries` 每个 port,
   ChannelEgine 用这些 entries 做 .asc 合成

→ cal cert → simulator 链路实际是 **lazy DB lookup + 两层 silent fallback**
(precheck 不算 gate, 因为不阻断)。Cert 没灌好 → precheck 只 warn, measure
phase 照样跑, 用典型值算 .asc, **没人会报错**。

当前规避: GUI commissioning workflow 主观上是"先 calibration tab 后 commission",
operator 不太会忘 — 但**没有 code-level 安全 net**。triage 见
[`roadmap-first-call.md`](../roadmap-first-call.md) "Discovered during" backlog 区。

---

## 还缺的 testing 覆盖

P0-7 + P1-7 验证基本上都是**直接 import ChannelEgine library 调函数**, 没真打
HTTP layer。原因是 api-service + channel-engine-service 共用 namespace, 同
pytest session import 会冲突。

生产代码用真 httpx → :8001, 但 pytest 里:

- ❌ 没端到端跑过 HTTP (api-service POST → 微服务 receive → 微服务 import CE → 返回)
- ❌ 没在 pytest 里独立验证微服务 FastAPI handler

**已知 gap**, 跟 P0-7 留下的是同一个。技术债, 不影响 production, 但下次 namespace
冲突解决方案上桌时一并修。

---

## 落实文档的目的

1. 把 P1-7 整条 wire-up 第一次完整闭环这件事**留个版本快照**
2. 标记四个 surprising 点 — 防 future 工程师踩坑
3. 把 ring-only silent constraint 显式连到 P2-7 — 防"忘了我们还有这个 gap"
4. 给将来上 PWS / 真 PA dynamic compensation 留 stub (在四个 surprising 点
   里都已经标了"将来怎么扩")
