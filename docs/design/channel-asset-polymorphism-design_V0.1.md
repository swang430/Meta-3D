# 信道资产多态化设计 V0.1（草案）

> 状态：**决策已定（2026-06-28，用户拍板）** —— §6 终态独立「信道工作台」+ 渐进迁移；§7 起步软件半全做（S1–S4）。经命名 / RT 输入形式 / 来源-路径分层**三轮问答厘清深化**（§2 洞察 2 修正 + §3.1 亲和性 + §3.2 命名契约）。本设计据此拆 roadmap（见 §8 → 已落 `roadmap-first-call.md`）。
> 关联：[[P2-14 B-2 信道注入]]、[[P2-15 自定义 CDL]]、`RT-MPDB-CDL-F64-channel-injection-design_V1.0.md`、
> memory `project_b2_universal_channel_injection_design` / `project_testcase_driven_instrument_arch` /
> `project_scd_frontend_consumption_gap` / `project_ota_probe_baseband_rf_two_layer`。
> 编写依据：2026-06-28 三路代码考古（横切骨架+GCM+文件栈 / ASC+custom CDL / B-2+RT+MPDB），全部 `file:line` 已核实。

---

## 0. 目的与范围

把当前**四分五裂**的四种信道源——GCM native、B-1 ASC 烘焙、B-2 参数化 TDL、RT 动态合成——统一为单一的**多态「信道资产」实体**，对 TestCase 暴露一个 `channel_asset_id`，取代现在的 `scd_id` / `cdl_profile_id` / `asc_source_path` / `config.extra` 裸 RT dict 四套并行引用。

本设计回答两件事，并为之后的 roadmap 规划埋点（**本设计不排期**）：

1. **统一抽象长什么样**（§2–§5）：实体模型、来源/路径解耦、管线路由。
2. **信道资产的 GUI 该跟 DUT/SIM 同栏，还是独立成一个接口**（§6）——这是用户的核心问题。

**非目标**：不在本轮实现 B-2 `.tap` 字节生成、RT 数据接入、F64 真机验证（全是现场半，见 §7）。

---

## 1. 现状：四源四分五裂（代码事实）

### 1.1 资产形态 / 引用契约 / 耦合 对照

| 源（用户口径） | `EngineMode` | strategy | **资产形态** | **引用契约** | 持久实体 | 强耦合 | GUI 入口 |
|---|---|---|---|---|---|---|---|
| GCM native | `keysight_gcm` | `NativeModelStrategy` | 外部 `.smu` **文件指针**（内容 F64 黑盒） | `scd_id`（SCD 实体）/ 裸 `emulation_file` | **SCD**（✅全栈） | F64（内容不可控） | 仪器抽屉 `StandardChannelDefinitionCard`（CRUD） |
| B-1 / ASC 标准 | `mimo_first_asc` | `ExternalWaveformStrategy` | **瞬态合成** `.asc`（按 `frequency+cdl_model_name` 现合成，无持久资产） | `cdl_model_name` 字符串 | ❌ | channel-engine-service | TestCase 内 `.smu` 下拉（标称名） |
| B-1 / ASC 自定义 | `mimo_first_asc`+`cdl_profile_id` | 同上 `_synthesize_custom_cdl` | **参数实体**（静态簇，单快照） | `cdl_profile_id`（实体，但**不进频率一致性网**，strategy 内 fail-loud） | **CustomCDLProfile**（✅全栈，P2-15） | AssetProfiles 第 3 Tab（簇编辑器） |
| （debug）外部 ASC | `external_asc` | `ExternalAscPathStrategy` | 本机 `.asc` **目录路径** | 裸 `asc_source_path` 字符串 | ❌ | 无（应急/调试） |
| B-2 参数化 TDL | `b2_parametric_tdl` | `B2ParametricTdlStrategy` | **RT 射线参数 dict** → 参数表 → `.tap`（现场半） | `config.model_extra` 裸 dict（`rt_rays`/`test_class`/`f64_profile`） | ❌（无实体） | 无 |
| RT 动态合成 | （未独立 engine_mode） | （F4/F5 library-only） | **多快照** `AnnotatedCDLProfile`（簇生灭+轨迹） | 无 | ❌（仅微服务 Pydantic，未落库） | 无 |

### 1.2 三个结构性断层

- **断层 A — 资产载体三类不可通约**：文件指针型（GCM/external）vs 瞬态合成型（ASC 标准）vs 参数型（custom/RT）。「参数 → 文件」的烘焙，在 ASC 路是 MIMO-First 可控（`.asc`），在 GCM/B-2 路是 F64 厂商黑盒（`.smu`/`.tap` 只能现场生成）。
- **断层 B — 时变能力只存在于未落库的容器**：唯一能表达「per-snapshot 演化 + 簇身份 + 生灭」的是 ChannelEgine 的 `AnnotatedCDLProfile`（snapshots/trajectory_meta），但它**无 MIMO-First DB 实体**。`CustomCDLProfile` 是它的静态单快照退化子集，表达不了动态。
- **断层 C — 能力悬空 + 分流是校验非路由**：F4 时空跟踪、F5 phase_continuous、`b1_annotated_baker` **算法写好但无端点消费**；§6 路径判决（`select_path_and_clustering`）能算出该走 B-1/B-2/GCM，但执行器层只拿它做一致性 fail-loud，**不按判决结果切 strategy**。

---

## 2. 核心洞察

### 洞察 1：「资产来源」与「注入路径」是两个正交维度，被 `EngineMode` 揉成了一维

当前 `EngineMode` 同时编码了「参数从哪来」和「怎么落硬件」，导致 B-2/RT 无处安放、custom CDL 只能寄生在 `mimo_first_asc` 里。解耦后：

| 维度 | 取值 | 含义 |
|---|---|---|
| **来源 source**（资产是什么） | `standard_3gpp` / `custom_static` / `rt_dynamic` / `vendor_file` | 参数从标准库 / 操作员手编簇 / RT 射线 / 厂商 `.smu` 而来 |
| **路径 target**（怎么注入） | `asc_baked`(.asc) / `b2_parametric`(.tap) / `gcm_native`(.smu) / `external`(.asc 目录) | 由 §6 判决 + test_class + 硬件能力**决定**，不由操作员直接选 |

**一个来源可走多条路径**：同一组 custom 簇，低多普勒可烘 `.asc`(B-1)，落 F64 native 谱可 native_fit 成 `.tap`(B-2)。**RT 来源天然分流到三路**——这正是用户说的「RT 综合前 3 能力」的机制本质（§6 判决就是这个分流器）。

> 结论：多态实体描述的是**来源**；**路径是判决产物**。用户列的「B-2 参数化 TDL」严格说不是一种*资产来源*，而是 `custom_static`/`rt_dynamic` 经 native_fit 后的一种*注入路径*。

### 洞察 2：统一载体已经在 ChannelEgine 侧浮现 —— `AnnotatedCDLProfile`

它的三层结构（`AnnotatedCDLProfile → CDLSnapshot[] → AnnotatedCluster`）+ `doppler_repr` 判别联合体，已经能装下全部四源：

| `doppler_repr.kind` | 承载语义 | 落地路径 | 对应源 |
|---|---|---|---|
| `baked` | 多普勒烘进 CIR | `.asc`/.ir (B-1) | custom_static 低多普勒 / 标准 |
| `native` / `dual_gaussian` | F64 闭式谱 + 质心/展宽 | `.tap` (B-2) | custom_static / rt_dynamic 吞吐类 |
| `subray_sum` | 确定性子径相干求和 | `.asc`(B-1) / 交 GCM | rt_dynamic 确定性类（ISAC/波束） |
| 多 `snapshots[]` + `trajectory_meta` | 簇跨快照身份+生灭+演化 | 多 environment `.rtc` | rt_dynamic |

且 `from_custom_profile()` 已证 `CustomCDLProfile ≡ AnnotatedCDLProfile` 的单快照退化。**所以多态化的技术核心 = 把 `AnnotatedCDLProfile` 提升为 MIMO-First 持久实体**（设计 V1.0 §11 开放问题 #4 已预告），`CustomCDLProfile`/SCD 收口为它的特例。

> **修正（2026-06-28 厘清）**：上表易误读为「`AnnotatedCDLProfile` 也是统一的*资产存储*」。准确说它是统一的**合成中间表示**——各来源装配/聚类后汇聚到它，但**资产存储形态各异**：`custom_static` 存簇（≈ ACP 单快照，退化重合，故易混淆）；`rt_dynamic` 存**原始 MPDB 射线**（`MPCInput`），ACP 是它合成时聚类的*产物*而非存储。原因见 §3.1：聚类策略由 `test_class` 驱动，只存聚类后会把路径焊死、丢失重聚能力。

---

## 3. 目标抽象：`ChannelAsset` 判别联合体

```
ChannelAsset (持久实体, 表 channel_assets)
├── id / name(unique) / description / is_active / 时间戳 / created_by    # 资产档案壳（与 DUT/SIM 同构）
├── source_type: Enum{standard_3gpp | custom_static | rt_dynamic | vendor_file}   # 判别键
├── canonical_name: str?      # 确定性派生名（vendor/standard/rt 有，custom 为 null），见 §3.2
├── derived_from: str?        # provenance（custom 自标准 CDL「另存」/ rt 快照固化出身），见 §3.2
├── allowed_targets: [str]    # 路径亲和集，判决在此集内选，见 §3.1
├── 声明物理（一致性网用，全 nullable）: center_frequency_hz / bandwidth_mhz / is_los / k_factor_db / ue_velocity_mps
└── payload: JSONB（按 source_type 多态；存「资产原始输入」，非聚类后的合成中间表示，见 §2 洞察 2 修正）
      standard_3gpp →  { cdl_model_name }                       # 标称名，瞬态合成，可不落 clusters
      custom_static →  { snapshots:[ 单快照{clusters[...]} ] }   # = 现 CustomCDLProfile.clusters
      rt_dynamic    →  { snapshots:[ 多快照{rays:[MPCInput…]} ], sampling_meta, scenario_meta }   # 原始 MPDB 射线，非聚类后 CDL
      vendor_file   →  { scd_config{band,arfcn,bw,model,scenario,...}, associated_file_path:.smu }  # = 现 SCD
```

要点：

- **payload 形态随 `source_type` 变**（判别联合体，不是大一统扁平表）：`vendor_file` 是文件引用（GCM 黑盒），`standard_3gpp` 是枚举选择，`custom_static`/`rt_dynamic` 才是真参数集。这忠实反映「GCM 内容不可控 / RT 是时变 / custom 是静态簇」的物理现实。
- **`b2_parametric` 不是 `source_type`**：它是 `custom_static`/`rt_dynamic` 经 native_fit 的输出路径（§2 洞察 1）。
- **统一频率一致性门**：所有 `source_type` 的 `center_frequency_hz` 都进 Phase 1 多方一致性网（现在 `scd_id` 进、`cdl_profile_id` 不进——这个不一致一并消除）。
- **TestCase 侧收敛**：`scd_id`/`cdl_profile_id`/`asc_source_path`/裸 RT dict 四字段 → 收敛为单一 `channel_asset_id`（保留旧字段一版做 backward-compat 映射，见 §4.2）。

### 3.1 来源 ⊥ 路径：亲和性、统一判决、RT 资产工厂（2026-06-28 厘清）

来源层（what）与路径层（how）是两个抽象层，不是叠加关系——**所有来源都在三条路径之上**，经判决投影到路径层。但来源→路径不是全连接，受**路径亲和性 `allowed_targets`** 约束：

| source_type | `allowed_targets` | 说明 |
|---|---|---|
| `vendor_file` | `{gcm_native}` | 携带 `.smu` artifact，F64 GCM 引擎直接加载 |
| `standard_3gpp` | `{asc_baked}` | 标称 CDL 烘 `.asc`；要走 GCM 改用 `vendor_file`（关联 F64 预置 scenario `.smu`） |
| `custom_static` | `{asc_baked, b2_parametric}` | 手编簇可 B-1，native-fit 后可 B-2 |
| `rt_dynamic` | `{asc_baked, b2_parametric}` | 原始射线烘 B-1 / 聚类 B-2；判决指向 GCM → ESCALATE（见下） |

> **`gcm_native` 是 artifact-backed 路径**（Codex #172 P2）：F64 GCM 引擎只吃编译好的 `.smu` scenario，不吃 `cdl_model_name` / 原始射线。所以**只有携带 `.smu` artifact（`associated_file_path`）的资产才能路由到 `gcm_native`** —— 否则动态路由会 late-fail 或静默加载驱动默认 `.smu`（P2-12「默认 .smu 陷阱」）。推论:`vendor_file` 天然可走；`standard_3gpp` / `rt_dynamic` **不可走** —— 标称名 / 原始射线无 `.smu`，且 RT 射线 → GCM 几何参数的逆向拟合未建模，判决指向 GCM 时走 **ESCALATE**（与 §6 一致）。这正是 §1 洞察「GCM 内容 F64 黑盒，MIMO-First 不能从参数凭空生成 `.smu`」在路由层的落地约束。

三条设计后果：

1. **统一判决器**：所有来源过同一 §6 `select_path_and_clustering`，**只是约束不同**（在 `allowed_targets ∩ test_class 可行集` 内选）。`vendor_file` 退化成单选，`rt_dynamic` 判决空间最大。不给任何来源独立判决通道。
2. **RT 的「之上」是信息包含，不是层叠**：RT 是唯一物理真值（真实射线）+ 唯一时变（多快照轨迹，需 F4）+ 判决空间最广（B-1/B-2 可落地；判决指向 GCM 时因无 `.smu` artifact 走 ESCALATE）。信息论上**其他来源是 RT 的有损投影**——有 RT 能聚出 standard-like / custom-like / B-2 native，反之不能从抽象模型还原原始射线。
3. **RT 作为资产工厂**：RT 某快照的聚类结果可**固化成 `custom_static` 资产**（`derived_from` = RT 场景 + 快照号），供无 RT 数据时复用。RT 与其他来源是**生成关系**而非并列。

### 3.2 命名契约：承袭 SCD，分三族（2026-06-28 厘清）

SCD（[`channel_naming.py`](../../api-service/app/services/mimo_ota/channel_naming.py)）确立的原则：**有规范配置真值源的资产，名字 = 从离散规范维度确定性派生、双向可逆、软件拥有命名权**（不赌厂商约定）。推广到四源 = 两个名 + 三族：

- 每个 `ChannelAsset` 有 `name`（human label，unique，所有资产都有）+ 可选 `canonical_name`（确定性派生，担去重/审计/确定性引用，= SCD 唯一约束的推广）。
- **族 A — SCD 确定性派生族**（有规范维度）：`vendor_file` = 现 SCD `MF_<band>_<arfcn>_BW<bw>_<model>_<scenario>_<mimo>_<pol>_v<ver>.smu`；`standard_3gpp` **复用同一命名函数**（规范维度与 SCD 重合，差别只在后缀/落地 `.asc` vs `.smu`）→ 印证两者本是一族。
- **族 B — RT 派生族**：`rt_dynamic` 从 **RT 场景元数据**派生（`RT_<scenario>_<route>_<v>kmh_<fc>_v<ver>`，**不是**从簇参数派生，因为存的是原始射线）；维度 schema 待 S5 接 RT-Release 时定。
- **族 C — 自由命名**：`custom_static` 无规范源（操作员任意编簇，拼不出有意义标准名）→ 只有自由 `name` + `derived_from`（从哪个标准 CDL「另存」起编）。`canonical_name = null`。

---

## 4. 数据模型与迁移

### 4.1 表草案（`channel_assets`，PG，JSONB+SQLite variant）

| 列 | 类型 | 说明 |
|---|---|---|
| `id` | UUID PK | |
| `name` | String unique | 资产名 |
| `source_type` | String/Enum | 判别键 |
| `canonical_name` | String nullable unique | 确定性派生名（族 A/B 有，custom 为 null），§3.2 |
| `derived_from` | String nullable | provenance（custom 另存来源 / rt 快照固化出身），§3.2 |
| `allowed_targets` | JSONB/Array | 路径亲和集，判决在此集内选，§3.1 |
| `center_frequency_hz`/`bandwidth_mhz`/`is_los`/`k_factor_db` | Float/Bool nullable | 声明物理（一致性网） |
| `ue_velocity_mps` | JSONB nullable | `[x,y,z]` |
| `payload` | JSONB NOT NULL | 多态主体（对齐 `AnnotatedCDLProfile`） |
| `instrument_connection_id` | FK nullable | 仅 `vendor_file` 用（SCD 的连接归属） |
| `associated_file_path` | String nullable | 仅 `vendor_file`(.smu) / 未来 `b2` 现场关联(.tap) |
| `is_active` | Bool | 软删 |

### 4.2 现存实体的收口（backward-compat，零破坏）

| 现状 | 收口为 | 迁移方式 |
|---|---|---|
| `CustomCDLProfile`（P2-15） | `ChannelAsset(source_type=custom_static)` | 数据迁移：clusters→`payload.snapshots[0].clusters`；旧 `cdl_profile_id` 在 measure 层映射到 `channel_asset_id`（一版兼容） |
| `StandardChannelDefinition`（SCD） | `ChannelAsset(source_type=vendor_file)` | scd 配置→`payload.scd_config`；`scd_id`→`channel_asset_id` 映射 |
| `cdl_model_name`（标准选择） | `ChannelAsset(source_type=standard_3gpp)` 或保持轻量枚举 | 标准选择无需落库，可只在引用时 resolve（**待定**，见 §7 决策点 2 的子问题） |
| B-2 `config.extra` 裸 RT dict | `ChannelAsset(source_type=rt_dynamic)` | RT 数据接入时直接建资产（现场半，§7） |

> 风险护栏：迁移须对 PG / SQLite-brownfield / SQLite-greenfield 三路径测试（memory `feedback_addcolumn_migration_dialect_agnostic`）；新增字段走 4 步契约同步（`feedback_api_contract_sync_after_pydantic_change`）+ 全 fan-out audit（`feedback_new_field_fanout_audit`）。

---

## 5. 管线：从「校验」到「路由」

接线把 §1.2 断层 C 补上：

1. **资产 → 装配**：`ChannelAsset.payload` → `AnnotatedCDLProfile`（custom_static 走单快照退化；rt_dynamic 直接装配；vendor_file 直接给文件路径；standard_3gpp 走 `Standard3GPPBuilder`）。
2. **判决路由（新）**：`AnnotatedCDLProfile` + `test_class` + 硬件能力 → §6 `select_path_and_clustering` → `target_path` → **动态选 strategy**（取代现在执行器层的 fail-loud-only）。这需要接线 F4（多快照轨迹）/F5（确定性相位）/`b1_annotated_baker`（B-1 烘焙入口），消解 library-only 悬空。
3. **落地**：`asc_baked`→微服务出 `.asc`；`b2_parametric`→`extract_tap_parameters`→（现场）`.tap`；`gcm_native`→F64 `.smu`；`external`→本机目录。

> 探头几何在 `asc_baked` 路进**基带**合成（`simulator.py:961` `W_base` 探头权重乘进复数 CIR）+ 射频校准 `1/H_sys`，两层都消费（memory `project_ota_probe_baseband_rf_two_layer`）——多态实体不改变这一点，资产只描述「信道」，探头展开仍在合成层。

---

## 6. 决策点 1：GUI 归属 —— 跟 DUT/SIM 同栏 vs 独立工作台

### 6.1 判据矩阵

| 维度 | DUT / SIM | 信道资产（多态后） | 倾向 |
|---|---|---|---|
| 数据形态 | 扁平声明字段表 | 多态 + 时变 + 嵌套簇/快照 | → 独立 |
| 内部交互复杂度 | 填表 | 簇编辑器 + native-fit 残差 + 聚类质量 + test_class→路径预览 + RT 轨迹可视化 | → 独立 |
| 与硬件耦合 | 无（纯声明） | 一半天然属仪器语境（GCM `.smu`/B-2 `.tap`/F64） | → 独立 |
| 现状是否已分裂 | 否 | **是**：SCD 在仪器抽屉 / custom CDL 在 AssetProfiles（两处） | → 独立（收口分裂） |
| 引用模式 | TestCase 引 `*_id` | TestCase 引 `channel_asset_id`（同构） | → 同栏 |
| 操作员心智 | 「测什么对象」 | 「测什么环境 + 怎么合成/注入」（有算法纵深） | → 独立 |
| 改动成本（短期） | — | 同栏改动小（custom CDL 已在） | → 同栏 |

### 6.2 决策（已定 2026-06-28）：**终态独立「信道工作台」，渐进迁移**

理由：信道资产与 DUT/SIM 只有「被 TestCase 按 ID 引用」这一点同构，其余维度（多态、时变、可视化纵深、硬件耦合、现有分裂）都指向独立。值钱的 IP（native_fit / 时空跟踪 / 路径判决）都在信道侧，值得一个专门工作台暴露其能力，对标 Channel Studio。DUT/SIM 留在 AssetProfiles 作「被测对象声明」，语义更纯。

**但不推翻现状、不大爆炸**，渐进四步：

- **G0（现状）**：custom CDL 在 AssetProfiles 第 3 Tab —— 保留，过渡合理。
- **G1**：后端建 `ChannelAsset` 多态实体，custom CDL + SCD 收口（**GUI 不动**，纯后端 + backward-compat 映射）。
- **G2**：建独立「信道工作台」页，把 AssetProfiles 的 custom CDL Tab + 仪器抽屉的 SCD 卡片迁入，统一为 `source_type` 切换的单一资产管理界面（收口 §1.2 + `project_scd_frontend_consumption_gap` 的分裂）。
- **G3**：工作台接 RT 动态（多快照 + 轨迹可视化）+ test_class→路径判决可视化；B-2 现场可执行后暴露 engine/路径选择（接 roadmap P2-14 第 4 项「GUI 暴露」）。

---

## 7. 决策点 2：起步范围 —— 现场依赖边界

| 能做（软件半，不依赖现场） | 现场半（阻塞，等现场） |
|---|---|
| `ChannelAsset` 实体 + CRUD + 多态 payload schema | `.tap` 字节序列化（Channel Studio 专有） |
| custom CDL / SCD 收口 + backward-compat | 真实 RT 射线数据接入（Lauraycs RT + RT-Release） |
| 装配层 `payload → AnnotatedCDLProfile` | F64 真机验证（.tap schema / gaussian 谱 / .rtc 抖动 / f_upd_max） |
| 接线 F4/F5/baker（消解 library-only）+ §6 判决路由（用合成 RT 测） | `F64CapabilityProfile` 阈值现场标定 |
| 独立信道工作台 GUI（G2）+ custom/SCD/standard 三 source_type | rt_dynamic 资产的真实数据填充 |
| 单快照 `b2_parametric` 参数表（已有 `extract_tap_parameters`） | 多快照 `.rtc` 多 environment |

**起步范围（已定 2026-06-28）= 左列软件半**：实体统一 + 装配 + 判决路由 + 独立工作台 GUI（G1+G2 + custom/SCD/standard 落地），全部本地可测、零现场依赖。rt_dynamic 与 b2 `.tap` 落地随 B-2 现场（P2-14 收尾）走 S5/S6。

> 子问题（待定，不阻塞起步）：`standard_3gpp` 标称选择**是否需要落 `ChannelAsset` 实体**，还是保持轻量枚举即时 resolve？倾向后者（标准选择无自定义参数，落库是冗余），但若工作台要「统一列出所有可选信道」则前者更一致。G2 设计时定。

---

## 8. 对 roadmap 的输入（已落 `roadmap-first-call.md` → P2-16）

候选切片（依赖关系：S1→S2→S3 串行；S4 可与 S2/S3 并行；S5/S6 挂现场）：

| 切片 | 内容 | 现场依赖 |
|---|---|---|
| S1 | `ChannelAsset` 实体 + migration（PG/SQLite 三路径）+ CRUD + 多态 payload schema | 否 |
| S2 | custom CDL + SCD 收口（数据迁移 + `cdl_profile_id`/`scd_id`→`channel_asset_id` backward-compat） | 否 |
| S3 | 装配层 `payload→AnnotatedCDLProfile` + §6 判决路由（接线 F4/F5/baker，合成 RT 测） | 否 |
| S4 | 独立「信道工作台」GUI（G2）：source_type 切换 + 簇编辑器迁入 + SCD 卡片迁入 + 浏览器实测 | 否 |
| S5 | rt_dynamic 资产真实数据接入 + 多快照 | **是**（RT-Release） |
| S6 | `b2_parametric` `.tap` 落地 + F64 验证 + GUI engine 暴露（P2-14 第 4 项合流） | **是**（Channel Studio + F64） |

---

## 附：关键代码锚点（考古核实）

- 横切：`base_generator.py:16-72`（EngineMode + BaseChannelGenerator）；`measure.py:458-577`（无集中工厂的 if/elif 分流 + 统一载荷 + `cdl_profile_id` 一致性门 `:568`）。
- GCM/文件栈：`gcm_strategy.py:52-193`；`standard_channel.py:34-94`(SCD)；`standard_channel_service.py:178-198`(`resolve_emulation_for_measure`)；`emulation_file_gate.py:73-115`。
- ASC/custom：`asc_strategy.py:48-219`（`_synthesize_custom_cdl:157`+频率门`:177`+is_los 门`:188`）；`channel_engine_client.py:234`/`:435`/`:128`(CDLCluster)/`:157`(装配)；`custom_cdl_profile.py:27-50`。
- B-2/RT/MPDB：`b2_parametric_strategy.py:52-116`（恒 return False=现场半）；`b2_cluster.py:48-109`(`cluster_b2_native`)；ChannelEgine `annotated_cdl_schema.py:25-79`(`doppler_repr` 联合体)/`geometric_native_fit.py:207-249`(F3)/`spatiotemporal_tracking.py:66-149`(F4,未接线)/`phase_continuous.py:66-95`(F5,未接线)/`b1_annotated_baker.py`(未接线)/`path_decision.py:63-133`(§6)。
- 设计依据：`RT-MPDB-CDL-F64-channel-injection-design_V1.0.md` §3.3/§6/§7/§8.2/§9/§11。
