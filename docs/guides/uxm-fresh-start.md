# UXM fresh-start 配置 runbook (P1-17)

> 全新部署 / HAL reload 时 UXM (Keysight 基站仿真器) 怎么**自动就位到默认配置**,
> 以及怎么覆盖。对称 F64 的默认 .smu 自动加载 —— 让现场不再"走快速路"(手动前面板
> 点 / 临时 PUT 选 profile)。

## 自动行为 (P1-17)

HAL reload → `RealUxmDriver.connect()`:
1. **Test App 检测**:`SYSTem:APPLication:NAME?` 确定哪个 Keysight 软件在跑
   (5G_NR_Test / LTE_NR_IRAT),据此选 SCPI 命令 profile。driver 只检测、不设置 —
   UXM 上跑哪个 Test App 由前面板/前置决定。
2. **默认 topology profile 自动应用**:`_initialize_from_db` 若发现 binding 的
   `connection_params` **没显式选** `topology_profile_id` → fallback 到驱动的系统
   默认 `caict_n78_3600_4x4`(3600M / N78 / 4x4),自动 `apply_topology_profile`。

结果:UXM 一键就位,cell 频率/MIMO 跟 F64 默认信道**同频**,无需手动选 profile。

## ⚠️ 为什么默认必须是 3600M

F64 默认 .smu = `3GPP_FR1_OTA_CDLC_UMa_3600M`(N78, 4-input, **3600 MHz**)。UXM 默认
profile **必须同频 (3600M)** —— 否则 BS 发 3600 而信道仿真器在别的频 = 链路打架,
fresh-start"一键就位"反而配出错的链路。`caict_n78_3600_4x4` 专门对齐 F64 默认;现有
`caict_n78_4x4` (3500M) 保留不动 (其它引用可能依赖)。

## 覆盖默认 (优先级 高 → 低)

| # | 方式 | 作用域 | 怎么做 |
|---|---|---|---|
| 1 | binding 显式选 profile | 这个 UXM binding | `PUT /api/v1/instruments/baseStation/topology-profile` `{profile_id}`(GUI 拓扑选择器)→ 持久化 `connection_params["topology_profile_id"]` |
| 2 | binding 改 fallback 默认 | 这个 UXM binding | `connection_params["default_topology_profile_id"] = "<id>"`(改这个 binding 的默认 fallback,对称 F64 `default_emulation_file`)|
| 3 | 代码全局默认 | 所有 UXM | `UXM_DEFAULT_TOPOLOGY_PROFILE_ID`(`app/hal/uxm_base_station.py`)= `caict_n78_3600_4x4` |

`_initialize_from_db` 解析顺序:`binding.topology_profile_id`(#1)→ `driver._default_topology_profile_id`(#2 binding override 或 #3 代码默认)。

## 内置 profile (8 个)

`siso_n78_100m` / `siso_n78_low_power` / `caict_n78_2x2` (3500M) / `caict_n41_2x2` /
`caict_n78_4x4` (3500M) / **`caict_n78_3600_4x4` (3600M, fresh-start 默认)** /
`cal_power_sweep` / `cal_2x2_alt_port`。

源:`app/hal/uxm_test_profiles.py`(in-code registry)→ bootstrap `topology_profiles`
seeder 持久化到 `instrument_topology_profiles` 表(`is_system_preset=True`)。

## 验证 fresh-start 是否就位

```bash
# HAL reload 后, 看 baseStation 检测到的 Test App + 当前选中 profile
curl -s localhost:8000/api/v1/instruments/baseStation/topology-profiles | \
  python -m json.tool   # 看 selected_topology_profile_id + current_test_app
```
readiness 面板的 baseStation 行也会显示 `detected_test_app` + `command_profile`。

## 已知 deferred (见 roadmap P1-17 / U-7)

- **现场半**:real UXM 上 fresh-start 一键就位实测(cell live + 对齐 F64 频率)+
  remote `.state` 文件盘点(U-7)。
- **`.state` 一键 recall**:`load_state_file` 机制已有,但"默认 .state 自动 recall"
  的 override(对称默认 profile)本期未做,留后续。
