# FS16 SMU playback 传导测试联调记录

> 日期: 2026-06-11  
> 设备: Keysight PROPSIM FS16 / F8820A, `192.168.0.100`  
> 目标: 基站仿真器和终端指标保持 mock, 信道仿真器使用真实 FS16, 通过 GUI 跑一次 FS16 hybrid KPI smoke  
> 当前状态: 软件侧 FS16 playback + hybrid KPI 通路已补齐并通过单测; 下次现场主路径优先使用 HiSLIP, raw `5025` 仅保留为诊断项

## 一句话结论

本轮已经确认: 这次传导测试应加载 FS16 上的 `.smu` playback/session 文件, 不是 `.asc` 文件。软件侧已补齐 FS16 playback 驱动、GUI 参数入口、诊断序列、hybrid KPI smoke 和并发 SCPI 保护。由于现场已验证 HiSLIP `*IDN?` 正常而 raw `5025` 曾超时, 下次主路径改为 `TCPIP0::192.168.0.100::hislip0::INSTR`; raw `5025` 只用于排查 FS16 raw SCPI 服务状态。

## 本次完成的工作

### 1. FS16 playback 驱动补充

新增 FS16 playback 扩展驱动, 不改已有 F64 驱动:

- `api-service/app/hal/propsim_fs16_playback.py`
- 在 driver registry / HAL bootstrap 中把 Keysight PROPSIM FS16 绑定到 `RealPropsimFs16PlaybackDriver`
- 支持 FS16 默认目录 `D:\User Playbacks`
- 支持配置项:
  - `remote_playback_file`
  - `verify_remote_file_exists`
  - `auto_start_after_load`
  - `enable_scpi_file_upload`
  - `playback_entry_file`
- 默认加载命令:
  ```text
  MMEM:LOAD:STAT "{path}"
  ```
- 默认启动 / 停止命令:
  ```text
  DIAG:SIMU:GO
  DIAG:SIMU:GOS
  ```

### 2. GUI 配置入口补充

在仪器资源配置的 FS16 卡片中补充了参数输入:

- FS16 内 `.smu` playback 文件名或完整路径
- 加载前校验文件存在
- 加载后自动开始播放
- 本机上传入口文件名, 目前仅保留为实验性入口

同时修正了误导文案:

- 原先界面和 smoke 中出现过 `playback/ASC`
- 已改为 `.smu playback`
- hybrid smoke 默认示例改为 `Emulation0609.smu`
- Sequence Runner 会把 `base_station_mode` 渲染成 `mock/real` 下拉选择, 避免现场手输模式出错

### 3. FS16 playback smoke 诊断序列

新增诊断序列:

- `api-service/app/diagnostics/sequences/fs16_playback_smoke.py`

用于单独验证真实 FS16:

1. `connect channelEmulator`
2. `FS16 load playback <file.smu>`
3. 可选 `FS16 start playback`
4. 可选运行若干秒后 stop

这个序列刻意不走旧的 conducted passthrough, 适合当前“CE real, BS/SA mock”的 bring-up。

### 4. SCPI 终端 query 判断修复

修复了 `MMEM:CAT? "D:\User Playbacks"` 这种“问号后面还有路径参数”的命令识别问题。之前这类命令可能被当成 write, GUI 显示 `(OK, no response)`; 修复后会按 query 读取目录响应。

### 5. FS16 SCPI 并发保护

在 `api-service/app/hal/propsim_fs16.py` 中给 FS16 单 VISA/socket 会话加了 `_io_lock`, 串行化所有 `_query/_write`。

修复的现场问题:

- 后台 monitoring 每秒查询 `DIAG:SIMU:STATe?`
- smoke 同时执行 `MMEM:LOAD:STAT` / `*OPC?` / `SYST:ERR?`
- 两者共用同一 session 时曾出现响应错位, 例如 `*OPC?` 读到 `0,"No error"`、`SYST:ERR?` 读到 `1`
- 这就是此前 `FS16 playback load failed: 1` 的主要原因

锁加上后, 响应顺序已恢复正常。

### 6. 错误显示改善

`connect channelEmulator` 失败时, smoke 现在会把驱动的 `last_error` 带出来, 后续不再只显示泛泛的:

```text
RuntimeError: driver returned False
```

而是能显示类似:

```text
VI_ERROR_TMO (-1073807339): Timeout expired before operation completed.
```

### 7. FS16 hybrid KPI smoke

新增诊断序列:

- `api-service/app/diagnostics/sequences/fs16_hybrid_kpi_smoke.py`

用于今天目标的完整软件闭环:

1. `channelEmulator`: real FS16 playback driver
2. `baseStation`: 默认 mock driver
3. `DUT/终端 KPI`: 默认 mock 指标
4. `FS16 verify playback file Emulation0609.smu`
5. `FS16 load playback Emulation0609.smu`
6. 可选 `FS16 start playback`
7. 配置虚拟基站参数并采样 KPI

关键参数:

```json
{
  "remote_playback_file": "Emulation0609.smu",
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

保护逻辑:

- `base_station_mode=mock` 时, 如果 HAL 实际加载了 real baseStation, 序列会拒绝执行并提示切回 mock, 避免误碰真实基站。
- 后续接真实基站时, 改成 `base_station_mode=real` 并在前端把 baseStation driver mode 切 real 即可复用同一骨架。
- Sequence Runner 结果卡会显示 `CE real / BS mock / DUT mock` 和 KPI 摘要表。

## 已验证结果

### 软件测试

相关单测通过:

```text
api-service/tests/test_propsim_fs16_playback_driver.py
api-service/tests/test_fs16_playback_diagnostic_sequence.py
api-service/tests/test_fs16_hybrid_kpi_sequence.py
api-service/tests/test_scpi_command_timeout_passthrough.py
api-service/tests/test_conducted_diagnostic_sequence.py
```

关键结果:

```text
57 passed
gui npm run build passed
```

### FS16 目录可见性

FS16 `D:\User Playbacks` 能通过 SCPI 看到文件。曾确认过:

```text
MMEM:CAT?
```

返回中包含:

```text
mimo0609.smu
```

后续用户重新放入:

```text
Emulation0609.smu
```

### 文件格式判断

`.asc` 不是这次 FS16 playback smoke 的正确目标文件。现场现象:

- `link0.asc` 会触发 missing 或 `SMU file corrupt or missing`
- FS16 playback/session 应使用 `.smu`
- `.asc` 仍可能是其他 pipeline 的中间产物, 但不是当前 FS16 smoke 的首选输入

### SMU load 行为

`mimo0609.smu` 可见后, 软件实际发过:

```text
MMEM:LOAD:STAT "D:\User Playbacks\mimo0609.smu"
```

以及当前目录 + 裸文件名变体:

```text
MMEM:CDIR "D:\User Playbacks"
MMEM:LOAD:STAT "mimo0609.smu"
```

也试过泛化写法:

```text
MMEM:LOAD "mimo0609.smu"
```

都能执行到 `*OPC? = 1`, 但当时 FS16 对 `mimo0609.smu` 返回:

```text
-300,"Device-specific error;SMU file corrupt or missing"
```

判断: 当时的 `mimo0609.smu` 不是 FS16/F8820A 当前状态可加载的有效 playback/session 文件, 或者内部依赖缺失。

### 最新现场状态

用户重新放入 `Emulation0609.smu` 后, smoke 运行约 5 秒失败, 失败发生在第一步:

```text
connect channelEmulator
```

后端验证结果:

```text
nc -vz 192.168.0.100 5025
Connection succeeded

nc -vz 192.168.0.100 4880
Connection succeeded
```

但 raw socket `*IDN?` 超时:

```text
TCPIP0::192.168.0.100::5025::SOCKET
*IDN?
VI_ERROR_TMO
```

HiSLIP 可正常返回:

```text
TCPIP0::192.168.0.100::hislip0::INSTR
*IDN?
Keysight Technologies,F8820A,MY62500170,10.2
```

HAL reload 后 readiness 显示:

```text
channelEmulator: fail
fail_kind: scpi
detail: VI_ERROR_TMO (-1073807339): Timeout expired before operation completed.
```

判断: FS16 主机和网络还活着, 但 `5025` raw SCPI 服务当前不返回响应。此时不要继续换 `.smu`; 主路径改用 HiSLIP, raw `5025` 作为独立故障分支记录。

## 当前旁路故障

当前旁路故障:

```text
FS16 raw SOCKET 5025 accepts TCP but does not answer SCPI queries.
```

表现:

- `nc` 到 `5025` 成功
- `*IDN?` 在 `5025` 上超时
- `4880` HiSLIP `*IDN?` 正常
- 旧 raw endpoint 配置会导致后端 HAL 无法加载 `channelEmulator`
- 使用 HiSLIP endpoint 后, 该故障不应阻塞主路径

推断:

- 不是网线断
- 不是 IP 配错
- 不是文件名问题
- 不是后端旧会话未释放, 因为独立 PyVISA raw socket 会话也超时
- 更像 FS16 raw SCPI 服务被当前 playback/simulation 状态卡住, 或仪器软件需要关闭当前 simulation / 重启应用 / 重启仪器; 但这不再是 hybrid KPI smoke 的前置条件

## 下次工作推进计划

### Phase 0: 使用 HiSLIP 主路径连接 FS16

目标: 让软件主路径通过 `TCPIP0::192.168.0.100::hislip0::INSTR` 控制 FS16。raw `5025` 不再作为主路径前置条件。

步骤:

1. 在前端仪器资源配置中选择:
   - `channelEmulator`: `PROPSIM FS16`
   - driver mode: `real`
   - endpoint: `TCPIP0::192.168.0.100::hislip0::INSTR`
2. 推荐保持全局 HAL 为 `Mock`, 然后只把单台 `channelEmulator` 的 driver mode 设为 `real`。HAL 的混合模式语义是: 全局 `Mock` 下, 单仪器 `real` 仍会加载真实驱动。
3. 将 `baseStation` 暂时设为 `mock`, 或保持全局 HAL 为 `Mock` 且 `baseStation` 跟随 `auto`。不要把全局 HAL 切到 `Real` 后让 `baseStation` 也跟随 `auto`, 否则后续有真实 UXM/CMW500 配置时可能会尝试连接真实基站。
4. GUI 点击“重载 HAL 驱动”。
5. 在 GUI 或后端 SCPI 终端测试:
   ```text
   *IDN?
   ```
6. 成功应看到:
   ```text
   Keysight Technologies,F8820A,MY62500170,10.2
   ```
7. 如果 HiSLIP 也超时, 再停止 FS16 本机当前 simulation/playback, 重启 FS16 控制软件或仪器。

辅助判断:

```bash
nc -vz 192.168.0.100 5025
nc -vz 192.168.0.100 4880
```

注意: `nc` 成功只代表 TCP 端口开, 不代表 SCPI 可用; 主路径必须以 HiSLIP `*IDN?` 返回为准。raw `5025` 超时只记录为故障分支, 不阻塞 hybrid KPI smoke。

### Phase 1: 重载 HAL 并确认真实 FS16 驱动

HiSLIP `*IDN?` 成功后:

1. GUI 点击“重载 HAL 驱动”, 或调用:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/instruments/hal/reload
   ```
2. 确认 readiness:
   ```bash
   curl http://127.0.0.1:8000/api/v1/instruments/hal/readiness
   ```
3. 期望:
   ```text
   channelEmulator status=ok
   detail=RealPropsimFs16PlaybackDriver
   endpoint=TCPIP0::192.168.0.100::hislip0::INSTR
   ```

### Phase 2: 确认 `Emulation0609.smu` 在 FS16 上可见

在信道仿真器 SCPI 命令终端执行:

```text
MMEM:CDIR "D:\User Playbacks"
MMEM:CAT?
```

期望返回中有:

```text
Emulation0609.smu
```

如果看不到:

- 文件不在 SCPI 当前可见的 `D:\User Playbacks`
- 或文件名大小写/扩展名不一致
- 或 FS16 UI 看到的目录与 SCPI 工作目录不同

### Phase 3: load-only smoke

先不要自动 start, 只验证 load:

```json
{
  "remote_playback_file": "Emulation0609.smu",
  "verify_remote_file_exists": true,
  "start_playback": false,
  "stop_after_s": 0,
  "cleanup_on_finish": false
}
```

成功预期:

```text
connect channelEmulator
FS16 verify playback file Emulation0609.smu
FS16 load playback Emulation0609.smu
```

如果失败:

1. 立即读:
   ```text
   SYST:ERR?
   DIAG:SIMU:STATe?
   ```
2. 若仍是:
   ```text
   -300,"Device-specific error;SMU file corrupt or missing"
   ```
   则去 FS16 本机界面手动打开该 `.smu`, 检查是否缺依赖文件或版本不兼容。

### Phase 4: start smoke

load-only 成功后, 再启动 playback。建议首次用自动停止, 防止 FS16 长时间留在运行态:

```json
{
  "remote_playback_file": "Emulation0609.smu",
  "verify_remote_file_exists": true,
  "start_playback": true,
  "stop_after_s": 5,
  "cleanup_on_finish": true
}
```

成功预期:

```text
connect channelEmulator
FS16 verify playback file Emulation0609.smu
FS16 load playback Emulation0609.smu
FS16 start playback
wait 5s
FS16 stop playback
```

如果 load 成功但 start 失败:

1. 记录:
   ```text
   SYST:ERR?
   DIAG:SIMU:STATe?
   ```
2. 判断是否需要替换 start 命令模板:
   ```text
   DIAG:SIMU:GO
   ```
3. 若 FS16 UI 有明确的 start/play 命令名称, 再回填 `start_command` 配置。

### Phase 5: 跑 hybrid KPI smoke

FS16 load/start 通过后, 再跑当前目标的混合 smoke:

- channel emulator: real FS16
- base station: mock
- DUT / 终端 KPI: mock
- `.smu`: `Emulation0609.smu` 或现场确认可加载的文件名

在 Sequence Runner 选择:

```text
FS16 hybrid KPI smoke
```

默认关键参数:

```json
{
  "remote_playback_file": "Emulation0609.smu",
  "base_station_mode": "mock",
  "start_playback": true,
  "stop_after_s": 5,
  "cleanup_on_finish": true
}
```

此阶段目标不是测量准确性, 而是证明:

```text
GUI → 后端诊断序列 → HAL → FS16 load/start → mock BS 参数配置 → mock DUT KPI 展示
```

链路可复现。

成功结果卡应至少能看到这些关键步骤:

```text
FS16 verify playback file Emulation0609.smu
FS16 load playback Emulation0609.smu
FS16 start playback
BS set_cell_config ...
KPI window ...
BS stop_signaling
FS16 stop playback
```

如果 `DUT attach` 或 KPI 采样失败, 仍然检查结果步骤里是否出现 `BS stop_signaling` 和 `FS16 stop playback`。这两个步骤用于确认失败后软件已经尝试释放 mock BS 状态和真实 FS16 playback 状态; 若其中任何一个失败, 结果的 `cleanup_warnings` 会保留具体错误。

Sequence Runner 结果卡还会显示 `FS16 playback left running/stopped` 和 `BS signaling left running/stopped`。如果现场故意把 `cleanup_on_finish=false` 且 `stop_after_s=0`, 看到 `left running` 属于预期; 默认 smoke 应看到 `stopped`。

## 故障分支速查

| 现象 | 判断 | 下一步 |
| --- | --- | --- |
| `nc 5025` 失败 | TCP 不通 | 查网线/IP/子网/防火墙 |
| `nc 5025` 成功, `*IDN?` 超时 | raw SCPI 服务不响应 | 停止 simulation/playback, 重启 FS16 软件或仪器 |
| HiSLIP `*IDN?` 成功, raw `*IDN?` 超时 | FS16 主机活着, raw 5025 卡住 | 主路径继续用 HiSLIP; raw 5025 留作旁路故障修复 |
| `MMEM:CAT?` 看不到 `.smu` | 文件不在 SCPI 可见目录 | 确认 `D:\User Playbacks` 和文件名 |
| `.smu` 可见但 load 报 `-300` | 文件不可加载或依赖缺失 | 在 FS16 UI 手动打开/重新导出兼容 `.smu` |
| load 成功但 start 失败 | start 命令或 simulation 状态问题 | 读 `SYST:ERR?` / `DIAG:SIMU:STATe?`, 再调整命令模板 |
| 报 `driver returned False` 但无细节 | 旧 GUI/旧后端未刷新 | 重载后端/HAL, 使用新 smoke 显示 last_error |

## 下次现场需要带回的信息

如果仍失败, 下次请记录以下信息:

- FS16 UI 中 `Emulation0609.smu` 是否能手动打开
- FS16 UI 当前 simulation/playback 状态
- raw `5025` 的 `*IDN?` 返回或超时截图
- HiSLIP `4880` 的 `*IDN?` 返回
- `MMEM:CAT?` 的完整返回
- load 后的:
  ```text
  *OPC?
  SYST:ERR?
  DIAG:SIMU:STATe?
  ```
- FS16 固件版本, 当前已知:
  ```text
  Keysight Technologies,F8820A,MY62500170,10.2
  ```

## 相关文件

- FS16 基础驱动: `api-service/app/hal/propsim_fs16.py`
- FS16 playback 扩展驱动: `api-service/app/hal/propsim_fs16_playback.py`
- FS16 playback smoke: `api-service/app/diagnostics/sequences/fs16_playback_smoke.py`
- FS16 hybrid KPI smoke: `api-service/app/diagnostics/sequences/fs16_hybrid_kpi_smoke.py`
- SCPI 命令端点: `api-service/app/api/instrument.py`
- GUI 仪器资源配置: `gui/src/App.tsx`
- GUI Sequence Runner KPI 展示: `gui/src/features/Diagnostics/SequenceRunnerPanel.tsx`
- 测试:
  - `api-service/tests/test_propsim_fs16_playback_driver.py`
  - `api-service/tests/test_fs16_playback_diagnostic_sequence.py`
  - `api-service/tests/test_fs16_hybrid_kpi_sequence.py`
  - `api-service/tests/test_scpi_command_timeout_passthrough.py`
