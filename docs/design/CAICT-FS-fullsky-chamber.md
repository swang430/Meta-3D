# CAICT-FS —— 上半球"满天星"3D-MPAC 暗室配置设计

> **状态**：设计 + 已落入 Meta-3D（dev-fixture seeder，2026-06-06）。
> **动机**：CAICT 现有 16 位置双极化暗室以地平附近的环为主，只能覆盖近水平面的
> 到达角。CAICT-FS 在**上半球**（仰角 0°→90°）铺一层近似均匀的探头"满天星"，
> 把空间信道从"准 2D"升级到**全 3D**：支持 38.901 含 elevation 的 ZoD/ZoA 模型、
> 车顶天线的上行波束、以及高仰角入射场景。

---

## 1. 设计目标

- **上半球全覆盖**：仰角 0°（地平）到 +90°（天顶），方位 0–360°。
- **近似均匀角密度**（"满天星"）：每个仰角环的方位探头数按 `cos(仰角)` 递减，
  使球面上探头的角间距大致一致（≈30° 量级），而不是把探头都堆在地平环。
- **双极化**：每个物理位置同时有 V + H（物理上对应 ±45° 双极化探头），支持极化分集
  / XPR 建模。
- **与现有体系兼容**：复用 `chamber_configurations` + `probes` 模型，
  `probe_distribution="multi-ring"`，探头位置以球坐标 `{azimuth, elevation, radius}`
  存库，ChannelEngine Phase 8 直接读 DB 里的 `probe_positions`。

---

## 2. 探头布局（31 位置 × 双极化 = 62 通道）

环编号自顶向下（ring 1 = 天顶，与现有 32-probe 布局"ring 1 在最高仰角"的约定一致）：

| 环 | 仰角 | 方位数 | 方位步长 | 方位偏移 | 位置数 | 说明 |
|----|------|--------|----------|----------|--------|------|
| R1 | +90°（天顶） | 1 | — | 0° | 1 | 天顶单探头 |
| R2 | +60° | 6 | 60° | 0° | 6 | cos60°=0.5 → 半密度 |
| R3 | +30° | 12 | 30° | 15° | 12 | 与 R4 错开 15°，减少"辐条"对齐 |
| R4 | 0°（地平） | 12 | 30° | 0° | 12 | 水平基环（兼容现有横向覆盖） |

- **位置数** = 1 + 6 + 12 + 12 = **31**
- **探头通道** = 31 × 2 极化（V/H）= **62**
- 方位密度比：地平环 12 个（30° 间距）→ 60° 环 6 个（60° 间距）→ 天顶 1 个，
  角密度近似恒定（满天星）。R3 相对 R4 偏移 15° 做交错，避免所有探头落在同一批子午线。

> **可调旋钮**：把基环数从 12 改成 8/16、或加一个 +45° 环、或改方位偏移，都只是改
> `_RING_LAYOUT_FS` 一处常量再重新 seed。当前 62 通道是"30° 角分辨率"的一个均衡点，
> 不是硬性约束 —— 要更密/更稀说一声即可重生成。

---

## 3. 暗室 RF 参数（对齐 Type-D 车载全功能）

| 字段 | 值 | 说明 |
|------|----|----|
| `chamber_type` | `custom` | 非 A/B/C/D 标准型，特定部署 |
| `chamber_radius_m` | 4.0 | 车载大暗室 |
| `quiet_zone_diameter_m` | 1.0 | 静区直径（可按真车调） |
| `num_probes` | 62 | = 31 位置 × 2 极化 |
| `num_polarizations` | 2 | 双极化（V/H = ±45°） |
| `num_rings` | 4 | 见 §2 |
| `probe_distribution` | `multi-ring` | 多环 → ChannelEngine 读 DB probe_positions |
| `has_pa` / `pa_gain_db` | True / 20 | 下行功率放大 |
| `has_lna` / `lna_gain_db` | True / 20 | 上行低噪放（TIS 链路） |
| `has_duplexer` | True (25 dB iso) | 双向 |
| `has_turntable` | True (500 kg) | 车载转台 |
| `ce_bidirectional` / `ce_num_ota_ports` | True / 62 | 信道仿真器双向，OTA 端口 = 探头通道数 |
| `freq_min/max_mhz` | 400 / 7125 | FR1 全段 |
| `supports_trp / tis / mimo_ota` | True / True / True | 全功能（has_lna 满足 uplink-chain 门） |
| `is_system_preset` | False | 特定 lab 配置，可编辑（非只读模板） |
| `is_active` | **False** | 不抢占当前激活暗室；需显式激活/绑定（见 §5） |

---

## 4. 信道模型含义（为什么要上半球满天星）

- **2D ring（现状）**：探头集中在地平面，只能逼近方位面（azimuth-only）到达角谱 ——
  对 38.901 里有显著 elevation 扩展（ZoD/ZoA）的场景失真。
- **上半球 multi-ring（CAICT-FS）**：探头铺满上半球 → 能合成任意上半球到达角的平面波
  叠加，逼近完整 3D 空间信道。对**车顶天线**（主瓣朝上/斜上）、高楼/无人机/NTN 等
  高仰角入射尤其关键。
- 极化：每位置 V+H → 可注入 per-cluster XPR、极化分集，匹配 38.901 极化建模。

> 下半球（仰角 <0°）未铺探头：车载场景地面方向多被车体/地面遮挡，且上半球满天星已
> 覆盖主要入射立体角；需要全球面（如自由空间球形 MPAC）时再扩 R5/R6 到负仰角即可。

---

## 5. 如何在 Meta-3D 中使用

CAICT-FS 已通过 `api-service/scripts/dev-fixtures/seed_caict_fs_chamber.py` 落库
（chamber 行 + 62 探头行，幂等）。

- **查看探头布局**：GUI「探头与暗室配置」选 CAICT-FS → ProbeLayoutView 3D/2D 渲染满天星。
- **激活为当前暗室**（可选）：`PUT /api/v1/chambers/{id}`（或 GUI）设 `is_active=true`
  （会把其它暗室置非激活）。
- **绑定到 LabProfile**：`PATCH /api/v1/lab-profiles/{caict-lab-1-id}` 设
  `chamber_config_id=<CAICT-FS id>`，让 CAICT-Lab-1 用满天星暗室跑测试。
- **重新生成**（改密度后）：重跑 seeder（幂等：已存在则跳过；要强制重建先删旧行）。

参考：[`MPAC-OTA-Chamber-Topology.md`](MPAC-OTA-Chamber-Topology.md) · 数据模型见
`app/models/chamber.py` + `app/models/probe.py`。
