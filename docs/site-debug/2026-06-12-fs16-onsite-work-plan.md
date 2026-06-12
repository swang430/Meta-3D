# FS16 现场调试工作计划与操作步骤

日期: 2026-06-12  
目标: 真实 FS16 信道仿真器 + mock 基站 + mock DUT/KPI 的软件闭环确认  
主路径 endpoint: `TCPIP0::192.168.0.100::hislip0::INSTR`  
默认 `.smu`: `Emulation0609.smu`, 现场可改为真实文件名或完整路径  

---

## 0. 出发前软件侧结论

### 0.1 real/mock 模式不是后端写死

结论: **real/mock 由 GUI/DB/HAL 配置决定，后端没有把基站硬写成 mock。**

已核对链路:

1. GUI 仪器资源页有 driver mode 选择:
   - `Auto`
   - `Mock`
   - `Real`
   - 位置: `gui/src/App.tsx`
   - 行为: 调用 `PATCH /api/v1/instruments/{category_key}/driver-mode`

2. 后端 driver mode API 只保存选择:
   - `auto`: 跟随全局 HAL 模式
   - `mock`: 强制该仪器 mock
   - `real`: 强制该仪器 real
   - 位置: `api-service/app/api/instrument.py`

3. HAL 初始化时读取 DB 里的 `driver_mode` 决定加载 real 还是 mock:
   - `MOCK`: 默认 mock, 但单仪器 `real` 仍然会连接真实硬件
   - `REAL`: 默认 real, 但单仪器 `mock` 仍然会走 mock
   - `MOCK_FORCE`: 硬 mock, 会覆盖单仪器 `real`, 现场不要用这个模式跑 FS16
   - 位置: `api-service/app/services/instrument_hal_service.py`

4. `fs16_hybrid_kpi_smoke` 不会创建或强改 mock 基站:
   - 它只读取当前 HAL 已加载的 `baseStation` driver
   - 参数 `base_station_mode=mock|real` 只表达本次序列的期望
   - 如果 `base_station_mode=mock` 但 HAL 实际加载了 real BS, 序列会拒绝执行，避免误碰真实基站
   - 后续真实基站接入时，把 GUI 里的 baseStation driver mode 改 `Real`, 再把序列参数改 `base_station_mode=real`
   - 位置: `api-service/app/diagnostics/sequences/fs16_hybrid_kpi_smoke.py`

### 0.2 FS16 `.smu` 路径和文件名不是后端写死

结论: **FS16 文件名/路径可以在 GUI 或 Sequence Runner 里编辑，后端的 `Emulation0609.smu` 只是默认预填值。**

已核对链路:

1. GUI 仪器资源页 FS16 卡片可编辑:
   - `remote_playback_file`
   - `playback_entry_file`
   - `verify_remote_file_exists`
   - `auto_start_after_load`
   - `enable_scpi_file_upload`
   - 位置: `gui/src/App.tsx`

2. Sequence Runner 参数也可编辑:
   - `remote_playback_file`
   - `verify_remote_file_exists`
   - `start_playback`
   - `stop_after_s`
   - `cleanup_on_finish`
   - `base_station_mode`
   - 虚拟基站参数: `frequency_mhz`, `bandwidth_mhz`, `scs_khz`, `band`, `mimo_layers`, `dl_power_dbm`

3. FS16 driver 取文件名的顺序:
   - sequence 参数里的 `remote_playback_file`
   - 或 connection params 里的 `remote_playback_file`
   - 或兼容键 `playback_file` / `fs16_playback_file`
   - 位置: `api-service/app/hal/propsim_fs16_playback.py`

4. 路径规则:
   - 如果填完整路径, 例如 `D:\User Playbacks\Emulation0609.smu`, driver 直接使用完整路径
   - 如果只填文件名, 例如 `Emulation0609.smu`, driver 默认拼成 `D:\User Playbacks\Emulation0609.smu`
   - 默认目录来自 `playback_dir`, 也可以通过 connection params 覆盖

### 0.3 出发前软件测试结果

已运行:

```bash
cd api-service
.venv/bin/python -m pytest \
  tests/test_hal_mode_force_mock.py \
  tests/test_fs16_hybrid_kpi_sequence.py \
  tests/test_propsim_fs16_playback_driver.py \
  -q
```

结果:

```text
32 passed
```

前端:

```bash
cd gui
npm run build
```

结果:

```text
build passed
```

备注: Vite 仍有既有 chunk warning, 不影响本次现场流程。

---

## 1. 今日现场目标

本次不是正式射频性能测试，目标是打通软件控制链路:

```text
GUI
  -> 后端诊断序列
  -> HAL
  -> 真实 FS16 HiSLIP
  -> 校验 FS16 内部 .smu 可见
  -> load .smu
  -> start / stop playback
  -> mock baseStation 配置虚拟基站参数
  -> mock DUT attach
  -> mock KPI 展示
```

成功标准:

1. 软件能通过 HiSLIP 连接 FS16。
2. 软件能看到 FS16 内部 `.smu` 文件。
3. 软件能 load `.smu`。
4. 软件能 start playback。
5. 软件能 stop playback 或明确显示 left running。
6. baseStation 是 mock。
7. DUT/终端 KPI 是 mock 来源。
8. 结果卡能看到 KPI summary 和来源标识:

```text
CE real / BS mock / DUT mock
```

---

## 2. GUI 配置总览

### 2.1 仪器资源配置

| 类别 | GUI 设置 | 现场建议值 | 说明 |
|---|---|---|---|
| `channelEmulator` | 型号 | `PROPSIM FS16` | 绑定 `RealPropsimFs16PlaybackDriver` |
| `channelEmulator` | driver mode | `Real` | 真实连接 FS16 |
| `channelEmulator` | endpoint | `TCPIP0::192.168.0.100::hislip0::INSTR` | HiSLIP 主路径 |
| `baseStation` | driver mode | `Mock` | 今天不接真实基站 |
| DUT/终端 | 指标来源 | `Mock KPI` | 只验证软件流程 |

重要提醒:

- 不要用 `MOCK_FORCE` 跑今天这条 FS16 链路，因为它会把 FS16 也强制 mock。
- 可以用全局 `Mock` 加单仪器 `channelEmulator=Real`; HAL 逻辑允许这种组合。
- baseStation 当前应为 `Mock`; 后续接真实基站时再改为 `Real`。

### 2.2 FS16 文件参数

| 字段 | 在哪里改 | 建议值 | 说明 |
|---|---|---|---|
| `remote_playback_file` | 仪器资源 FS16 Playback 文件, 或 Sequence Runner 参数 | `Emulation0609.smu` | 可改成现场实际 `.smu` 文件名或完整路径 |
| `playback_dir` | connection params JSON | `D:\User Playbacks` | 只填文件名时使用这个目录 |
| `verify_remote_file_exists` | GUI switch 或 Sequence Runner 参数 | `true` | load 前先查目录 |
| `start_playback` | Sequence Runner 参数 | `true` | load 成功后是否 start |
| `stop_after_s` | Sequence Runner 参数 | `5` | smoke 后自动 stop |
| `cleanup_on_finish` | Sequence Runner 参数 | `true` | 结束时释放状态 |

---

## 3. 现场操作步骤

## Phase 0: 开机与网络确认

1. 确认电脑和 FS16 在同一网段。
2. 确认 FS16 IP:

```text
192.168.0.100
```

3. 确认 FS16 本机 UI 能看到目标 `.smu` 文件。
4. 首选确认文件:

```text
Emulation0609.smu
```

5. 如果现场文件名不同，记录真实文件名，后面在 GUI / Sequence Runner 改。

通过标准:

- FS16 本机可见目标 `.smu`
- HiSLIP endpoint 可用

失败处理:

- 文件不可见: 先在 FS16 本机修文件位置/文件名
- 网络不可达: 查网线、IP、交换机、电脑网卡地址

---

## Phase 1: 配置仪器模式并 reload HAL

1. 打开 GUI 仪器资源配置。
2. `channelEmulator`:

```text
model: PROPSIM FS16
driver mode: Real
endpoint: TCPIP0::192.168.0.100::hislip0::INSTR
```

3. `baseStation`:

```text
driver mode: Mock
```

4. 保存配置。
5. 执行 HAL reload。
6. 查看系统就绪/仪器状态。

通过标准:

- `channelEmulator` 加载为 real FS16 driver
- `baseStation` 加载为 mock driver
- 没有真实 BS 被连接或启动

失败处理:

- FS16 real driver 未加载: 先做 SCPI probe / health probe
- baseStation 显示 real: 立即改回 Mock 并 reload HAL

---

## Phase 2: FS16 基础连通与目录确认

优先使用 HiSLIP:

```text
TCPIP0::192.168.0.100::hislip0::INSTR
```

raw 5025 只作为诊断:

```text
192.168.0.100:5025
```

建议确认命令:

```text
*IDN?
SYST:INFO?
DIAG:SIMU:STATe?
MMEM:CDIR?
MMEM:CAT?
SYST:ERR?
```

通过标准:

- `*IDN?` 返回 Keysight / F8820A / FS16 相关信息
- `SYST:INFO?` 能确认 PROPSIM FS16
- `MMEM:CAT?` 或 hybrid verify step 能看到目标 `.smu`

失败处理:

- HiSLIP 不通: 查 VISA resource / 网络 / FS16 远控状态
- raw 5025 超时: 不要阻塞主路径，先继续 HiSLIP
- 目录不对: 填完整 `D:\...\xxx.smu` 路径，或改 `playback_dir`

---

## Phase 3: FS16 playback smoke

先跑单独 FS16 playback smoke，不引入 mock BS/KPI。

### 3.1 load-only

Sequence:

```text
fs16_playback_smoke
```

参数:

```json
{
  "remote_playback_file": "Emulation0609.smu",
  "verify_remote_file_exists": true,
  "start_playback": false,
  "stop_after_s": 0,
  "cleanup_on_finish": false
}
```

通过标准:

```text
connect channelEmulator
FS16 load playback Emulation0609.smu
```

### 3.2 start/stop

参数:

```json
{
  "remote_playback_file": "Emulation0609.smu",
  "verify_remote_file_exists": true,
  "start_playback": true,
  "stop_after_s": 5,
  "cleanup_on_finish": true
}
```

通过标准:

```text
connect channelEmulator
FS16 load playback Emulation0609.smu
FS16 start playback
wait 5s
FS16 stop playback
```

失败处理:

- load 失败且 `SYST:ERR?` 出现 corrupt/missing:
  - 去 FS16 本机 UI 手动打开 `.smu`
  - 检查 `.smu` 依赖文件、版本兼容、路径
- start 失败:
  - 记录 `DIAG:SIMU:STATe?`
  - 记录 `SYST:ERR?`
  - 检查 start command 模板是否适配当前 FS16 firmware

---

## Phase 4: Hybrid KPI smoke

Sequence:

```text
fs16_hybrid_kpi_smoke
```

推荐参数:

```json
{
  "remote_playback_file": "Emulation0609.smu",
  "verify_remote_file_exists": true,
  "start_playback": true,
  "stop_after_s": 5,
  "cleanup_on_finish": true,
  "base_station_mode": "mock",
  "frequency_mhz": 3500,
  "bandwidth_mhz": 100,
  "scs_khz": 30,
  "band": "n78",
  "mimo_layers": 2,
  "dl_power_dbm": -50,
  "throughput_windows": 3,
  "throughput_window_s": 0.2
}
```

必须看到的步骤:

```text
connect channelEmulator (FS16)
FS16 verify playback file Emulation0609.smu
FS16 load playback Emulation0609.smu
FS16 start playback
connect baseStation (mock)
BS set_cell_config ...
BS set_downlink_power ...
BS start_signaling ...
DUT attach
query_ue_capability
KPI window ...
BS stop_signaling
FS16 stop playback
```

结果卡必须看到:

```text
CE real
BS mock
DUT mock
KPI: mock baseStation / mock DUT
```

KPI 表至少关注:

- DL throughput
- UL throughput
- DL BLER
- UL BLER
- CQI
- Rank Indicator
- MCS DL / MCS UL
- RSRP
- SINR

注意:

- 这些 KPI 是 mock 指标，只证明软件链路和结果展示。
- 不能作为真实射频性能结论。

---

## 4. 失败分支速查

| 现象 | 判断 | 处理 |
|---|---|---|
| `base_station_mode=mock` 但序列提示 HAL loaded real BS | GUI 中 baseStation 当前是 real | 立刻改 baseStation driver mode 为 Mock, reload HAL |
| `FS16 verify playback file` 失败 | FS16 目录中看不到文件 | 修正文件名、目录、或填完整路径 |
| `FS16 load playback` 失败 | 文件可见但 FS16 load 报错 | 查 `SYST:ERR?`; 在 FS16 UI 手动打开 `.smu` |
| `FS16 start playback` 失败 | load 成功但 start 命令失败 | 查 `DIAG:SIMU:STATe?`, `SYST:ERR?`, start command 模板 |
| KPI 没数据 | mock BS/DUT 流程失败 | 查 `baseStation` mock 状态和 sequence 参数 |
| 结果显示 `FS16 playback left running` | 没有自动 stop 或 stop 失败 | 手动 stop FS16 playback; 检查 cleanup warnings |
| raw 5025 超时 | raw socket 不稳定或未启用 | 不阻塞主路径, 继续 HiSLIP |

---

## 5. 停止标准

遇到下面情况不要继续往正式传导测试推进:

1. FS16 不能通过 HiSLIP 连接。
2. 目标 `.smu` 在 FS16 上不可见。
3. `.smu` 可见但 FS16 load 失败，且 FS16 UI 也打不开。
4. baseStation 意外加载为 real，但今天没有准备真实基站。
5. FS16 start 后无法 stop。
6. Hybrid smoke 无法显示 KPI summary。

---

## 6. 现场记录表

| 项目 | 现场记录 |
|---|---|
| FS16 endpoint | |
| FS16 `*IDN?` 返回 | |
| FS16 `SYST:INFO?` 返回 | |
| `MMEM:CDIR?` 返回 | |
| `MMEM:CAT?` 是否包含目标 `.smu` | |
| 目标 `.smu` 文件名/完整路径 | |
| `fs16_playback_smoke` load-only 结果 | |
| `fs16_playback_smoke` start/stop 结果 | |
| `fs16_hybrid_kpi_smoke` 结果 | |
| KPI summary 截图/diagnostic run id | |
| 异常 `SYST:ERR?` | |
| 异常 `DIAG:SIMU:STATe?` | |
| 需要回去改的软件点 | |

---

## 7. 关键源码索引

| 用途 | 文件 |
|---|---|
| HAL real/mock 决策 | `api-service/app/services/instrument_hal_service.py` |
| driver mode API | `api-service/app/api/instrument.py` |
| GUI driver mode 与 FS16 文件参数 | `gui/src/App.tsx` |
| FS16 playback driver | `api-service/app/hal/propsim_fs16_playback.py` |
| FS16 playback smoke | `api-service/app/diagnostics/sequences/fs16_playback_smoke.py` |
| Hybrid KPI smoke | `api-service/app/diagnostics/sequences/fs16_hybrid_kpi_smoke.py` |
| Sequence Runner 结果卡 | `gui/src/features/Diagnostics/SequenceRunnerPanel.tsx` |

---

## 8. 今日边界

今天只验证:

- 软件是否能控制真实 FS16
- 软件是否能加载/启动/停止 FS16 内部 `.smu`
- mock baseStation 是否能按虚拟基站参数生成 mock attach/KPI
- 前端是否能展示终端通信性能指标

今天不验证:

- 真实基站仿真器性能
- 真实 DUT 性能
- 暗室 OTA 校准结果
- 真实射频链路吞吐/Bler/SINR 结论

后续接真实 BS/DUT 时，路线是:

1. GUI 把 `baseStation` driver mode 改 `Real`
2. 填真实基站 endpoint
3. HAL reload
4. Sequence Runner 把 `base_station_mode` 改 `real`
5. 跑同类 smoke 或正式 TestPlan

