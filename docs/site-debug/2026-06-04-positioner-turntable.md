# 转台 (Aerotech Positioner) standalone 控制 + 现场 runbook (U-5)

> **日期**: 2026-06-04 | **Roadmap**: U-5 (转台无结论) + 关联 P0-5 | **来源**: 2026-05-27 现场
> **状态**: offline 半 (standalone 控制路径 + GUI 面板 + 测试) ✅ done;现场半 (真机验收) 🚧 待下次现场

## 背景: U-5 "无结论" 真因

2026-05-27 现场: Aerotech A3200 `@ 192.168.0.16:8000` 连上了, positioner 真驱动加载成功 (3/7),
但**无法单独验证转台** —— driver 的 `move_to/home/position/stop` 只被 cal/QZ 服务内部调, **无
standalone HTTP 入口**; 通用 `scpi-command` 端点不兼容 AeroBasic (driver 用 `_send/_tx_rx` 非
`_query/_write`, 且 AeroBasic 查询不以 `?` 结尾)。铁律1 现场不加端点 → 当时 spawn offline chip 未做。
这就是 U-5 "无结论" + 转台检查一直留着的真相 (不是转台坏 / 协议不明)。

## 解法 (本 PR, offline 半)

补 **standalone 转台控制路径**, 现场连上即可经 GUI / Swagger 单独验证, 不依赖完整 cal 流程:
- 后端端点 `/instruments/positioner/{home,move,position,stop,sweep}` (app/api/instrument.py)。
- GUI: **调试维护页 → 转台控制 Tab** (回零 / 输入角度移动 / 读位置 / 急停 / 4 方位扫 + 结果表)。
- driver 本就就绪: `connect()` 做 ENABLE + 清错, `reset()` = HOME 回零, `move_to()` = MOVEABS +
  到位 + PFBK 回读, `get_position()` = PFBK, `stop()` = ABORT; **单轴回零已处理** (CAICT 当年卡点)。

## Aerotech 协议要点 (集成说明 .docx, 2026-04-25)

- 接口: ASCII over TCP Socket, **端口 8000** (控制器 Socket2Port, 上位机必须一致)。
- 控制器配置: Enable Ethernet Socket 2 + Socket2 = TCP server + Socket2Port 8000 + Socket2Timeout ≥ 10000。
- 命令 **LF 结尾**; 响应 ACK `%` / NAK `!` / FAULT `#`; 查询 ACK 后续读数据。
- 命令: `FAULTACK X` / `ENABLE X` / `HOME X` / `MOVEABS X <角> XF<速>` / `WAIT INPOS X` / `PFBK(X)` /
  `ABORT X` / `AXISFAULT(X)`。
- 单位: 最好 user units = degree (否则软件做 degree↔counts 换算, 系数来自机械传动比 × 编码器分辨率)。
- 单轴: 轴名以现场控制器为准 (CAICT 是单轴方位; Y 轴 PFBK NAK 是正常, 非连接故障)。

## 现场 runbook (下次现场, 保证顺利控制)

1. **控制器侧**: 确认 Ethernet Socket 2 = TCP server + Port 8000 + ASCII enable + Timeout ≥ 10000。
   先在 Motion Composer / Console 手验 `ENABLE` / `HOME` / `MOVEABS` / `PFBK` 通。
2. **软件侧**: GUI 仪器选 Aerotech + 填连接 `IP:8000` → 重载 HAL → readiness 见 positioner ✓ (单轴会
   标 single-axis)。
3. **standalone 验证** (调试维护 → 转台控制 Tab, 或 Swagger `/instruments/positioner/*`):
   - **读位置** — PFBK 通 + 轴名对。
   - **回零 (HOME)** — CAICT 当年卡的单轴回零, 重点验。
   - **移动到 90°** → 读位置确认 ≈ 90°。
   - **4 方位扫** → 0/90/180/270 全部 ✓ 到位 (默认 ±0.5°)。
4. **验收角度一致性** (.docx §7): 分别测 0/90/180/270/360, 确认 GUI 显示角度 = 物理角度。若超差 →
   查 degree/counts 换算系数 (不靠经验猜)。
5. **接 P0-5**: 转台几何验证通过后, 4 方位扫 + 每方位触发吞吐测量 → 4 个不同吞吐值 (P0-5 验收)。

## 现场缺口 / 安全注意

- 真机 user units (degree vs counts) 现场确认; counts 则填换算系数。
- 轴名 (X / 其它) 以控制器为准, 填 driver config `azimuth_axis`。
- **急停 / 门禁 / 限位安全互锁由有资质人员确认** —— 软件 `ABORT` 不替代硬件急停。
- 速度 (XF) 按转台规格设; 暗室测量串行互锁 (转台到位 + 速度归零 + 无故障才触发采集)。

## 参考

- 协议: `Instrument_API_Doc/Aerotech/Aerotech_Ensemble_ASCII_TCP转台控制集成说明.docx`
- driver: `api-service/app/hal/aerotech_positioner.py` (协议行为测试 `tests/test_aerotech_*`)
- 端点: `api-service/app/api/instrument.py` (positioner 段) + 测试 `tests/test_positioner_control_endpoints.py`
- GUI: `gui/src/features/Diagnostics/PositionerControlPanel.tsx`
- 现场背景: [`2026-05-27-morning-log.md`](2026-05-27-morning-log.md) §10
