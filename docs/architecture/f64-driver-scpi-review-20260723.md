# F64 驱动 SCPI 全量 Review 报告（2026-07-23）

> **方法**：用 Keysight PROPSIM F64 厂商手册（NotebookLM「PROPSIM 资料」`982222b7`）对照
> 审查完整 `api-service/app/hal/propsim_f64.py`（3576 行 / 66 方法 / ~60 SCPI 命令），按
> SCPI 功能域切 5 块（会话 / 状态机 / 信道加载 / 输入侧 / 输出侧）并行 review，逐条查手册核实。
>
> **起因**：2026-07-21 现场全天耗在恢复 F64/UXM 会话 + 排障，没出吞吐数据。事后发现现场用的
> 临时脚本**不查源码**，重复了以前犯过的错（懒重连 2026-05-14 早已实现却手动重连）。借新接入
> 的 NotebookLM 资料库，把 F64 驱动一次性审到底。

---

## 一句话结论

**命令字面量大面积正确，病根只有一条：「该问仪器的地方在猜」。** 状态、频率、拓扑、端口全靠
本地缓存 / 文件名 / 硬编码常量 / 整机通道数去猜，而手册每一处都提供了权威回读命令
（`DIAG:SIMU:STATE?` / `DIAG:SIMU:MODEL:INFO?` / `CALC:FILT:CENT:CH?` / `GRO:IN:GET?` /
`GRO:OUT:GET?` / `OUTP:CALIB:VALid?`），驱动却几乎不用。

**约 29 个问题：P1≈6 / P2≈16 / P3≈7**，归为 7 条母题。

---

## 母题①：仿真状态全靠猜，`DIAG:SIMU:STATE?` 整个驱动零使用 ⭐最伤

`DIAG:SIMU:STATE?`（§20.4.3.14）返回 `CLOSED/OPENING/STOPPING/STOPPED/RUNNING/EDITING/CLOSING`，
是手册唯一的运行状态真值源。全仓 grep 确认**零调用**。

| 方法:行号 | 级别 | 问题 | 手册依据 | 建议 |
|---|---|---|---|---|
| `start_emulation:1420` | **P1** | GO 的 -200 豁免用 `STATIC?==0` 判"已在运行"——信号选错。**这正是 P2-1 (#221) 刚 merge 的修法：方向对（回读消歧）但信号错。** | §20.4.6.26 `STATIC?` 只报旁路档 0/1/2/3，不报运行态；§20.4.3.14 `STATE?==RUNNING` 才是。CLOSED 态 `STATIC?` 返回未定义 | 豁免改回查 `STATE?`，仅 `RUNNING` 豁免；读不到/非 RUNNING 一律 fail-loud |
| `get_metrics:2791` | P2 | 健康/监控读缓存 `_emulation_running`，不查真实态 | 同上；§20.6.1.2 `*OPC?=1` 不代表无错、不保证进 RUNNING | `get_metrics` 加 `STATE?` 回读，与缓存比对标注背离 |
| `_drain_after_timeout:3062` | P2 | 超时排水失败**不升级**去调已写好的 `_silent_reconnect_visa()`（只挂在 conn-lost 上） | ATE AN：crash/lockup 推荐 close+reopen socket 恢复 | 排水返回 False 时升级调 `_silent_reconnect_visa()`；免手动 kill 进程（现场痛点） |
| `set_bypass_mode:1774` / `clear_passthrough_mode:2062` | P2 | 进 bypass 时 `_emulation_running=False` 且丢弃"之前在跑"事实；清 bypass 只发 `STATIC 0` 不补回读 → 硬件自动续跑但驱动仍标停止 | §20.4.6.25 + ATE §2.4.5「若 bypass 前在跑，disabling bypass **continues the emulation**」 | `STATIC 0` 后回读 `STATE?` 同步 `_emulation_running`；或进 bypass 时保留 pre-bypass 态 |
| `disconnect:711` | P2 | CLOSE 被 `_loaded_emulation_file` 门控，冷缓存断开会把 F64 留在发射态 | ATE §2.2.2「CLOSE **can be always run**，fail-safe」 | disconnect 无条件发 CLOSE，与 start 冷缓存放行对称 |
| `stop_emulation:1497` | P3 | GOS 的 -200 豁免语义比"已停止"更宽 | 手册唯一记录的 GOS -200 是"nothing opened" | 被 STATE? 方案一并解决 |
| `set_bypass_mode:1759` | P3 | 非 DISABLED 复位重试中途 `STATIC 0` 会瞬时恢复衰落，与校准并发注入 RF 瞬变 | §20.4.6.25 运行态写 STATIC 0 自动续跑 | 重试前先 STOP/确认停止 |

> **DISABLED 分支（`set_bypass_mode:1718`）用 `STATIC?==0` 是对的**——那里目标就是确认旁路关闭，
> STATIC? 正是其 readback。只有 GO 判"运行态"误用了它。

**统一解法**：引入 `DIAG:SIMU:STATE?` 作状态真值源，GO/GOS/CLOSE 前先查状态决定动作或豁免。

---

## 母题②：端口/通道数靠猜，不查拓扑回读 ⭐直接影响校准正确性

**手册铁律**：`tx×rx` = **逻辑衰落通道数**，**不是**物理输出口数。MIMO 2x2 占 2 物理输入 +
**2 物理输出** + 消耗 **4 逻辑通道**（手册 3.1 拓扑节）。MPAC OTA 里物理输出口 = 探头数，来自
加载的 .smu 拓扑。真实激活口用 `MODEL:INFO?`（§20.4.3.6 → `<inputs>,<channels>,<outputs>`）/
`GRO:IN:GET?` / `GRO:OUT:GET?`（§20.4.7）读，且**激活口既不一定=tx 数、也不一定从 1 起连续**
（`INP:RSRP:MEAS?` 官方示例激活口就是 5,6,7,8）。

| 方法:行号 | 级别 | 问题 | 后果 |
|---|---|---|---|
| `set_path_loss:1292` + `get_metrics:2816` | **P1** | 物理输出口用 `tx×rx` 推 | **默认 3600M 是 32 探头，代码按 `4×4=16` 配 → 路损只设一半、17-32 全留工程默认**；或 2x2 时对不存在的 3/4 口下发 → 整条 NAK、路损没设上 |
| `set_baseband_power:1535` | P1 | 输入口 fallback 用 `range(1, _tx_antennas+1)`（P2-1 加了 `input_ports` 但默认仍是它） | 冷缓存/物理接 5-8 口时四路参考全设错口，端点仍回 ok=true |
| `set_channel_model:959` | P1 | CENT 频率循环全部 **64 硬件通道**（CALC:FILT:CENT:CH 是 per-group） | <64 通道模型对不存在通道报 -200 → 带频率 GCM 加载假失败 |
| `set_channel_model:938` | P1 | 拓扑硬编码 `(4,4)`，只对"文件==默认"同步 | operator 覆盖文件时 `_tx/_rx` 永远 stale → 下游全按错通道数配 |
| `get_metrics:2802` | P2 | 输入功率遥测同样假设 1..tx 连续 | 激活口 5-8 时遥测查 1-4 全记 None |
| `set_doppler:1334` | P2 | doppler 循环整机 64 通道 | 2x2 时向 emulation 外通道下发 → 假失败 |

**统一解法**：新增"从加载拓扑读真实激活输入/输出口"的 helper（`MODEL:INFO?` + `GRO:IN:GET?`/
`GRO:OUT:GET?`），读写两侧共用，替掉所有 `_tx_antennas` / `tx×rx` / `_channel_count` 推断。
`tx×rx` 只该用于 `set_mimo_config:1233` 对 64 容量的校验（那处是对的）。

---

## 母题③：频率靠文件名猜（系统性说谎）

| 方法:行号 | 级别 | 问题 | 手册依据 | 建议 |
|---|---|---|---|---|
| `get_frequency_identity:786` / `_parse_loaded_center_freq_mhz:761` | **P1** | 频率标识靠"programmed 标志 + 文件名解析"，从不回读仪器真值（`3600M.smu` 实为 3550） | §20.4.6.2 `CALC:FILT:CENT:CH? <ch>` 回读某组**实际**中心频 | 加载后每组一次 `CENT:CH? <代表通道>` 读真频作 identity 首选真值 |

> **直接消解 `project_f64_smu_filename_freq_mismatch` 记的 18 资产手工实测负担。**

---

## 母题④：load .smu 前置 CLOSE 盲发吞错（= 现场 load 失败根因，P0-3）

`set_channel_model:885` / `upload_asc_files:1061` / `load_parametric_tdl:553` 加载前 bare-write
`DIAG:SIMU:CLOSE`，错误随后被 `_drain_errors` 静默吞掉，既不查 STATE 也不确认真关掉。上次会话/GUI
遗留仿真处于瞬态时 → CLOSE 报 -200 没真关 → `CALC:FILT:FILE` 撞"已有仿真打开" → 30s 超时。
**这正是现场"load .smu 从没成功"的根因。**

### P0-3 手册化 load 序列（域 C 产出，带手册章节引用）

```
# ——加载前：确保干净且非瞬态——
*CLS                          # (§20.4.1.1) 清状态寄存器+错误队列；或复用 _drain_errors
DIAG:SIMU:STATE?              # (§20.4.3.14) 读状态
  ├ RUNNING            → DIAG:SIMU:STOP (§20.4.3.10) 再往下
  ├ OPENING/STOPPING   → 瞬态：*OPC? 等稳 / 重查，别硬发 CLOSE
  └ STOPPED/EDITING/其它 → 直接往下
DIAG:SIMU:CLOSE              # (§20.4.3.18)
DIAG:SIMU:STATE?             # ★复查 == CLOSED；不是就 fail-loud（别再往 FILE 走）

# ——加载（VISA 超时临时抬到 ≥40s，手册 §2.2.4：大文件 2000ms 默认必 -400）——
CALC:FILT:FILE <path>        # (§20.4.3.1) 反斜杠可能需双写；path 通常不加引号
*OPC?                        # (§20.4.1.7) 只表"执行完"，不表"成功"
SYST:ERR?                    # ★(§20.4.2.1) 必须 == 0,"No error" 才算加载成功
# VISA 超时恢复

# ——加载后回读（当前代码全缺）——
DIAG:SIMU:MODEL:INFO?        # ★(§20.4.3.6) → <inputs>,<channels>,<outputs>：确认加载 + 同步真实 tx/rx
CALC:FILT:CENT:CH? <代表通道>  # ★(§20.4.6.2) 读每组真中心频，作 identity 真值

# ——需覆盖 .smu 内置频率时，用 editing 模式（保 DUT 链路，手册推荐）——
CALC:FILT:EDIT <path>        # (§20.4.3.2)
GRO:GET? / GRO:CH:GET? <g>   # (ATE §3.2) 枚举组 + 每组代表通道
CALC:FILT:CENT:CH <代表>,<f>  # (§20.4.6.1) 只对每组代表发一次（不是 1..64！）
CALC:FILT:CONNECT            # (§20.4.3.3)
*OPC?  → SYST:ERR?

# ——启动（加载后默认停在 STOPPED，必须显式 GO）——
DIAG:SIMU:GO                 # (§20.4.3.8)
*OPC?  → SYST:ERR?  → DIAG:SIMU:STATE? == RUNNING 闭环确认
```

四个 ★ 是当前驱动相对手册的实质缺口：**CLOSE 后复查 CLOSED**、**加载后 `MODEL:INFO?` 回读拓扑**、
**`CENT:CH?` 回读真频**、**CENT 覆盖应 per-group 且优先 EDIT/CONNECT 而非 FILE 后逐 64 通道下发**。

---

## 母题⑤：禁盲试违反（connect 下发手册里不存在的命令）

| 方法:行号 | 级别 | 问题 | 正确命令 |
|---|---|---|---|
| `_probe_installed_options:3338` | P2 | interference license 探测用不存在的 `OUTPut:INTERFerence:LIST?` | `OUTPut:INTERFerence:GET?`（§20.4.9.5）**✅ P1-66 #382 已修：探针机制整体删除，能力单源 `SYSTem:INFO?`** |
| `_probe_installed_options:3343` | P2 | user-align license 探测用不存在的 `SYSTem:CALibration:USER:LIST?` | `SYSTem:CALIBration:LIST?`（§20.4.2.12）或 `USER:GET?`（§20.4.2.19，不受 license 门控）**✅ P1-66 #382 已修：同上，用户对齐走 `USER:GET?` 真值链** |

后果：每次 connect 打两条非法命令（-100）+ interference/user-align license **恒判缺失**（保证性
false-negative）→ 装了 K01 的机器 `set_calibration_tone` 被错误 gate 掉。且这两条查询在 connect 时
（还没加载 emulation）本就不可能工作。**建议直接退回 `SYST:INFO?` license 扫描。**

---

## 母题⑥：写命令假成功（无 fail-loud / 静默钳位）

Codex #202 R10「写→假成功」族的遗漏点。

| 方法:行号 | 级别 | 问题 | 建议 |
|---|---|---|---|
| `set_output_gain:1602` | P2 | 正增益被 F64 **静默钳位**（默认 `-45,0` dB，超限自动钳到最近值不 NAK）→ "放大补插损"卖点失效却返回 True | 下发前查 `OUTP:GAIN:LIMits?` 校验 fail-loud；大幅调整改用 P0-4 绝对电平 |
| `enable_user_alignment:2117` | P2 | 拼错/不存在的 name → F64 **新建空标定并激活**，`USER:GET?` 回读正好=该 name → 假成功（无真实标定跑测试报成功） | SET 前用 `CALIBration:LIST?` 确认存在，或 SET 后校验 `USER:INFO?` 含非空时间戳 |
| `get_output_calibration:2640` | P2 | 未标定(null) 与查询失败混淆（`float("null")` 抛 ValueError → 记 ERROR + 返回 None） | 先查 `OUTP:CALIB:VALid?`（0=not valid），valid=0 明确当"未标定" |
| `set_input_phase:2726` | P2 | 裸 write 后无条件 return True，无错误门（相位 ±200° 越界被拒只进队列不抛异常） | 改走 `_gated_write_transaction` |
| `set_runtime_environment:1131` | P2 | `CH:MOD:CONT:ENV` 写后无错误门；F64 R1.0 不支持运行时改 doppler，填 0 可能被拒 | 过 `_first_error` 门；doppler 位留空不填 0 |
| `set_center_frequency:2254` | P3 | 单通道 setter 裸 write 无错误门 | 套 `_first_error` + `CENT:LIMits?` 先夹范围 |

---

## 母题⑦：能力误判（把手册支持的能力注释成"不支持"）

| 位置 | 级别 | 问题 | 真相 |
|---|---|---|---|
| `propsim_f64_health.py:107` | P2 | `*OPT?` 标 CRITICAL → 真机健康检查**必然误报 BLOCKER** | `*OPT?` F64 ATE 不支持（-100），驱动本身已用 `SYST:INFO?` 替代；改非 critical 或删 |
| `propsim_f64.py:30/422/763` 注释 | P2 | 多处断言"F64 SCPI 不支持 MMEM" | 手册 §20.4.13 完整文档化 `MMEM:CAT?/DATA/DEL/...`；现场 -100 是本机固件/许可/早期错端口(5025)，**不等于 F64 不支持**。据此还弃了 `MMEM:CAT?` 动态发现信道模型清单（退回手填） |
| FTP `_ftp_upload_directory:3494` | P2 | Pipeline B/B-2 落盘依赖 FTP（手册全文不提，现场报不可用） | 官方文件传输是 `MMEM:DATA`（§20.4.13）；改走它，或先真机确认 FTP 开启 |
| `parse_f64_sys_info:258` | P3 | SYST:INFO? `parts[3]` 当 `firmware_version`，实为 **Device HW version**；真固件版本在 *IDN? 第 4 字段却没解析 | 更正字段映射 |
| `_clear_error_queue:3489` | P3 | `startswith("0")` 漏 `+0,"No error"`（`_first_error` 用 `int()==0` 是对的） | 复用 int 解析，或 connect 时发一次 `*CLS` |

---

## P0-4 手册化输出功率方案（域 E 产出）

roadmap P0-4 的痛点（逐口 `OUTP:GAIN:CH` 范围 -45~0 dB 不够、要整体输出命令）手册有明确答案：

1. **主力：绝对电平 `OUTPut:LEVel:AMPlitude:CH <output>,<dBm>`（§20.4.5.3）** —— 直接按 dBm 设每口
   平均输出，下发时该口 adjust mode 自动从 "Gain" 切 "Level"，**不受 -45~0 增益钳位**。新增 HAL
   方法 `set_output_level(output_num, level_dbm)` 用它。
2. **需正增益（放大 >0 dB）**：先 `SYSTem:MAXOUTGain:SET <dB>`（§20.4.2.7）抬全局上限（手册警告正
   增益下 RF 线性度/杂散不保证）。
3. **全局快速数字推高**：`DIAGnostic:SIMUlation:HIGHGAIN:SET 1`（§20.4.3.19），监控数字削波告警。
4. **F64 没有"一条命令设所有口"的全局绝对功率命令** —— 必须循环逐口 `OUTP:LEV:AMP:CH`，口径用
   **真实物理输出口数**（母题②，不是 tx×rx）。

---

## Roadmap 回填（2026-07-23 用户同意）

1. **新增 P0 大项「接入 `DIAG:SIMU:STATE?` 作状态真值源」** —— 母题①，一次解决 GO 豁免（含修
   P2-1 刚 merge 的）、健康检测、挂死恢复、bypass 漂移一串 P1/P2。
2. **新增 P0 大项「端口/通道数从拓扑回读」** —— 母题②，`MODEL:INFO?`/`GRO:*?` 替掉 tx×rx 和整机
   64，修 path-loss 配错口这条最伤校准的 P1。
3. **P0-3（load .smu 重写）** 直接采用母题④的手册序列（顺带把 `CENT:CH?` 频率回读接进去 = 母题③，
   消 18 资产实测）。**先开这个。**
4. **P0-4（整体输出功率）** 采用上面绝对电平方案。
5. **一个 P1 清理项**：两条禁盲试非法命令（母题⑤）+ 写命令 fail-loud 收敛（母题⑥）+ 健康检查
   `*OPT?`/MMEM 误判（母题⑦）。

**UXM 驱动同样值得照此 review**（本次只审 F64）。

---

## 元教训（写给流程）

1. **懒重连早有却没用上**：`0a3df3f`（2026-05-14）已把懒重连下沉到全 4 个 PyVISA 驱动，现场
   却还手动 `hal/switch`。根因是现场临时脚本**不查源码、凭印象**。→ 固化 rule
   `feedback_onsite_testcase_flow_no_adhoc_scripts`（现场走 TestCase 不写临时脚本）。
2. **todo 的"事实"行也要查代码**：P0-1 写"没有懒重连"是凭旧印象没查 git。→ 扩展
   `feedback_check_verifiable_state_yourself`（check-verifiable 也管"某能力代码里到底有没有"）。
