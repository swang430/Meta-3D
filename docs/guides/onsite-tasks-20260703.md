# 现场任务清单 — 2026-07-03 CAICT(信道模型下测吞吐)

> 执行细节与 go/no-go gate 见 [onsite-plan-throughput-under-channel-2026-07-02.md](onsite-plan-throughput-under-channel-2026-07-02.md);
> 铁律不重复:现场不写 driver 代码 / SCPI 探测 > GUI > RDP / 单 gate 卡 >半天就停。
> 状态列现场随手改:`[ ]` 待办 / `[~]` 进行中 / `[x]` 完成 / `[!]` 卡住(记原因)。

**基线**:tag `onsite-baseline-20260702` = main `f8f0dc9`;本分支 `onsite-20260703` 只收现场
discovered / 任务状态 / 数据登记,不进功能代码。

## 今日节奏规划(2026-07-03,按此执行;调整听 Simon 指令)

| 时段 | 任务 | 备注 |
|---|---|---|
| 到场 ~30min | **0 开机自检** | 软件侧清零未知数,再碰仪器 |
| 上午前段 | 1 Phase 0 网络 | 单网卡历史包袱:确认多网卡/adapter 方案,否则退回逐子网切换模式 |
| 上午中段 | 2 Phase 1 SCPI 握手 + 设备自检 | **检查点 A:午前必须过**,过不了=物理/网络问题,按协议排查不动代码 |
| 上午后段(间隙) | **6a 清点+选定信道文件** + 机动:队列清理拍板 | 6a 只需人在 F64 前,不依赖 DUT |
| 午后早段 | 3 Phase 2 SA 入 HAL | TRP 基线 ±1dB |
| 午后 | 4 Phase 3 真路损校准 | 机器自跑 ~32 链路,人闲 → 插机动项(仪器清单实化) |
| 午后中段 | 5 Phase 4 DUT attach | **记真实 IMSI** |
| 紧接 | **6b 合拍验证 + 6c 登记受控** | Phase 5 的入场券 |
| 午后晚段 | 7 **Phase 5 ★核心** | 切 Real + 重载 HAL → 一键脚本;**检查点 B = 今日成功判据** |
| 有余量才做 | 第二轮加严(机动):DUTProfile/SIMProfile 建档注入复跑 + 3.5GHz 反证频率网 | 非 go/no-go |
| ~17:30 | 8 收工 review + discovered 回填 + 分支推送 | 15 min |

**升级规则(贯穿全天)**:单 gate 卡 >半天且非纯硬件物理问题 → 停,整理 SCPI trace 远程协作;software 异常 = 记 discovered 不当场修。

## 主线任务(按序,gate 不过不进下一)

| # | 状态 | 任务 | 验收标准 | 落点 |
|---|---|---|---|---|
| 0 | [ ] | 开机自检 | 栈四绿(PG docker `meta3d_db` / :8000 / :5173 / :8001;重启过机先 `export CHANNEL_ENGINE_PATH=~/Tools/ChannelEgine` 再 `start_all_services.sh`)+ cockpit 驱动链/活动 Lab 绿(mock)+ 网络方案确认 | 控制 PC |
| 1 | [ ] | Phase 0 网络三子网可达 | F64 `nc -vz 192.168.0.x 3334` + UXM/SA 子网通 | 控制 PC 静态 IP 切换 |
| 2 | [ ] | Phase 1 SCPI 握手 | F64 `SYST:INFO?`(非 `*OPT?`)+ UXM Test App 起(5G NR FR1)+ SA IDN | 全 IDN ✓ |
| 3 | [ ] | Phase 2 真 SA 入 HAL(P0-4) | measured TRP 在 horn datasheet ±1 dB | GUI 选 FSVA3000 |
| 4 | [ ] | Phase 3 真路损校准(P0-3) | cert 32 链路 + overall_pass + 重复 ±0.5 dB,绑 lab 后 cockpit 校准格转绿 | CE+SA 路 |
| 5 | [ ] | Phase 4 DUT attach(P0-5) | attach ✓ + 单方位非零吞吐;**记下真实 IMSI**(Phase 6 脚本要用) | UXM |
| 6 | [ ] | ⭐ **确认与终端合拍的信道文件(我们能控制)** | 分三段插进节奏:**6a 清点+选定**(上午间隙,只需人在 F64 前)→ **6b 合拍验证**(Phase 4 后)→ **6c 登记受控**;展开见下 | F64 + 信道工作台 |
| 7 | [ ] | Phase 5 信道模型下 4 方位吞吐(★核心) | `DUT_IMSI=<真IMSI> ./scripts/onsite-run-channel-throughput.sh` → 4 方位 4 值 + analysis + PDF | 先切 Real + 重载 HAL |
| 8 | [ ] | 收工 review 三问 + discovered 行回填 | 当日 `[discovered on-site 2026-07-03 …]` 进本文档底部 | 15 min |

### 任务 6 展开:确认与终端合拍的信道文件(我们能控制)

**目标**:选定一个 F64 上真实存在、DUT 在其下能正常工作、且**参数我们完全掌握**的信道文件,
作为可复现测试的受控基准 —— 不是"随便哪个能跑的黑盒文件"。

- [x] **清点** —— ✅ 2026-07-03 上午 **SMB 突破**:F64 开匿名共享(`Scenario Packs`/`D`/`User Playbacks`/`CTIA MODEL`/`PROPSim`),Mac 直接 `mount_smbfs` 枚举,**不用人跑仪器前**。1.1 包实录:CDL-C × UMa/UMi × 9 频点(617/722/836.5/1575.42/1800/2132.5/2450/3600/4700 MHz)= 18 工程 + `4by32 cal.wiz`;`.cir` 文件名揭示拓扑 = **BS1→MS1 32x4 OTA DL**。共享根另见 `CAICT NR 4x4 OTA(SCC)`、`CTIA_Dynamic_OTA_UMa`、4 个 ENDC `.gcm`、LTE 包(现场可再挖)
- [x] **选定** —— ✅ `3GPP_FR1_OTA_CDLC_UMa_3600M.wiz\...smu` **存在性已经 SMB 远程实证**(ChannelAsset 声明路径逐字节确认在 F64 上)
- [ ] **合拍验证**:DUT 在该文件加载下 attach 稳定 + 吞吐非零(= 频段/带宽/层数与终端能力匹配)
- [ ] **登记受控**(缺一不算"我们能控制"):
  - [ ] ChannelAsset「F64 N78 场景文件」的关联文件路径 = 真实选定路径(出发前已预置为上述候选,若现场换文件在信道工作台改)
  - [ ] `scd_config` 身份与文件实际参数一致(arfcn 640000 / BW100 / CDLC / UMa / 4x4 / DP)
  - [x] 仪器抽屉 `available_channel_models` 清单更新为真实文件名 —— ✅ 2026-07-03 已换成 **18 条 SMB 实录**(demo 假名清除):label=SCD 命名规则 `MF_{band}_{arfcn}_BW100_CDLC_{UMa|UMi}_4x4_DP_v1`,filename=完整 `D:\` 路径(可直接喂 `CALC:FILT:FILE`),附 center_frequency_mhz + nr_arfcn(4700M 无整数 ARFCN 用标称槽)
- [ ] **一致性网实证**:故意把一次会话频率设 3.5 GHz 跑一发,确认 P2-11 网真的拦(可选,30 秒,给"网在工作"留证据)

**"我们能控制"两档(2026-07-03 晨读队友经验分享后升级)**:
- **档 1(保底,Phase 5 主路)**:选定 F64 上已知参数的现成文件(Scenario Pack CDLC UMa 3600M)→ 上面四步登记。
- **档 2(真·自控,时间富余才做)**:队友已备料 —— `docs/site-debug/现场经验共享/My model0702.json`(**23 簇自建模型**,含 ZoA/ZoD)+ `gcm_supported_cluster_import_{minimal,zoa_zod}.csv`(GCM 簇导入格式已验)。若现场 Channel Studio/GCM 可用:导入自建簇 → Generate Modeling Parameters(预览 PDP/角度)→ Generate Emulation → **必查 Level to DUT**(Min/Max/Range ≤ Max Level in HW)→ Save and Update → 得 .smu → F64 运行 + DUT 合拍。这才是完整的"我们能控制"闭环,也是 P2-16 自定义簇 → GCM 路的首次真机打通。

**GCM/FS16 经验速查(来自三篇分享,现场直接用)**:
- ⚠️ **工程文件整体保留,不要只拷 .smu**(.smu 引用外部信道数据,单拷会丢);
- 加载前礼仪:`*CLS → DIAG:SIMU:CLOSE → CALC:FILT:FILE → *OPC? → SYST:ERR? → DIAG:SIMU:GO`;
- 报 `-200 SMU file already open for editing` → 先 `DIAG:SIMU:CLOSE` 退编辑态再开;
- 报 `Emulator is not available` → PROPSIM 设备级重启,确认日志 `Selftests completed successfully`;
- 需要人在仪器 GUI 上操作(建模板/维护)→ 用软件的 **manual_local 控制权切换**(软件释放会话停轮询),做完再"软件接管" —— 别硬抢单 client SOCKET;
- CIR Graph 随编号持续跳动 = 动态信道正常回放;Port RF Level 空载无曲线**不代表** CIR 错;
- ⚠️ 三篇经验基于 **FS16**,F64 SCPI 已知有差异(MMEM/FTP/*OPT? 不可用,-100=命令不存在)—— `CALC:FILT:FILE`/`DIAG:SIMU:*` 在 F64 已实测可用,但 `CALC:FILT:EDIT` 编辑态流 F64 上未验,现场首次用时逐步 `SYST:ERR?` 确认。

## 机动任务(非阻塞,有空隙才做)

| 状态 | 任务 | 备注 |
|---|---|---|
| [ ] | 执行队列 ~99 条 5 月僵尸清理 | 需 Simon 拍板;`DELETE /api/v1/test-plans/queue/{plan_id}` 逐条 |
| [ ] | DUTProfile + SIMProfile 建档(真 DUT/SIM 到手后) | 建好后脚本注入 `dut_profile_id`/`sim_profile_id` 可活验三层能力/防插错网;首测不阻塞 |
| [ ] | 机器重启过则:`export CHANNEL_ENGINE_PATH=~/Tools/ChannelEgine` 再跑 `start_all_services.sh` | GCM 路不依赖 :8001,ASC 路要 |

**2026-07-03 现场决策记录**:① rfSwitch/EMCenter 免软件控制(通路已人工配置好,驱动 fail 不阻塞 —— precheck 实证 `critical_instruments_online: true`,rfSwitch 不在关键集);② bypass horn 参考天线静区测量(Phase 2 P0-4 TRP 基线不做),随之真路损校准(Phase 3)物理不可测一并跳过;③ Real 模式 4/7 驱动在线(F64/UXM/SA/转台),UXM 走 5125 TAF + LTE_NR_IRAT 方言。ad-hoc precheck 实测:**唯一剩余门 = DUT attach**。

## 当日 discovered(现场只记不修)

- `[discovered on-site 2026-07-03 during 任务6]` **F64 裸 SCPI 透传两坑(实证)**:① `CALC:FILT:FILE` 路径**不能带引号**(驱动的无引号形式才对,带引号必失败);② 一次错误后**该 socket 会话可能 wedge**——此后一切命令(含 `SYST:ERR?`)持续回 `-200 Wrong device state`、`*OPC?` 回 `-100.00000`,唯一解 = 重连会话(hal/switch 重载后同一仪器立刻 `0,"No error"`)。**规矩:F64 复杂操作一律走驱动路径**(自带 drain+长超时+fail-loud gate),`scpi-command` 透传只用于单条只读 query。UMi 3600M 加载本身**成功**(CLOSED→STOPPED,新会话确认)。
- `[discovered on-site 2026-07-03 during Phase4 前]` **UXM TAF 空闲断连实证(P2-4 母题)**:Real 重载后 ~15 分钟无命令,HAL 持有的 5125 socket 被对端掐(BrokenPipeError);修复 = hal/switch 重载。**操作纪律:闲置 >10 分钟后要跑 measure,先重载 HAL 再跑**;proper fix = 驱动周期 keepalive poke(P2-4)。
- `[discovered on-site 2026-07-03 during Phase4 前]` **UXM Test App 当前小区实配 DL ARFCN=636666(=3550 MHz)≠ 计划 3600**——Test App 启动自带态,非我们下发;等对齐决策(下发 640000 or UXM 面板手改)。
- `[discovered on-site 2026-07-03 during precheck]` **P1-8 校准门不区分校准数据来源(mock/real)** —— 昨晚 pre-departure 的 **mock** 路损校准(32 链路@3600)在今天 **real** 模式 precheck 里 `cal_pass: true`("VALID, age 12.6h, cert@3600 matches")。门只查存在性+频率+时效,不查 provenance → 真测里会应用 mock 补偿值,RSRP/绝对功率被静默污染。今日可接受(吞吐 smoke 不信绝对值),但 proper fix = cal 记录带 `use_mock` 标记 + real 模式 strict 门拒 mock cert(feedback_runtime_gate_not_frozen_snapshot 同族:live source 还要 live **provenance**)。

- `[discovered on-site 2026-07-03 during 任务6a]` **F64 SMB 匿名共享全开且可读** —— `Scenario Packs`/`D`/`User Playbacks` 等匿名可挂载;驱动注释预留的"走通 SMB 后动态发现 available_channel_models"路线**已实证可行**(今日已手动实录 18 条),后续可做成后端定期扫描/一键同步;顺带:匿名可写与否未测,若可写则 `.asc/.tap` 上传也可走 SMB 替代 FTP(P2-14/S6 相关)。
- `[discovered on-site 2026-07-03 during Phase1]` **UXM 平台 fw 3.39.0.2 对 `SYSTem:APPLication:NAME?` 回 -113**(Test App 未启动时整个业务 SCPI 树不存在)—— 驱动 Test App 探测若依赖此命令需兼容 -113=未启动的语义(比"超时"更快更明确的判据)。
- `[discovered on-site 2026-07-03 during Phase1]` **UXM 端点三层真相 + 驱动重定向条件漏 `inst0`** —— 实测:5025=平台(业务树 -113)/ **5125 raw socket = Test App Framework**(`C8700200A`,`SYSTem:APPLication:NAME?`→`LTE_NR_IRAT`,`BSE:CONFig:NR5G:CELL1:ACTive:STATe?`→1)。驱动的 Platform→hislip2 自动重定向只匹配 `SOCKET`/`hislip0` 资源串且显式配置时禁用,原绑定 `inst0::INSTR` 两条都不满足 → 真连会卡平台。**现场绕法(已做)**:绑定端点改 `TCPIP0::192.168.1.112::5125::SOCKET`,驱动 IDN 见非 Platform 不重定向、方言自动选 IRAT。**回家修法**:重定向条件补 `inst0`,或文档钉死"UXM 绑定一律写 TAF 端点"。今日运行 App=LTE_NR_IRAT(NSA/EN-DC),驱动 IRAT profile 覆盖,NR CELL1 已激活。
- `[discovered on-site 2026-07-03 during Phase0]` 现场布线实况:F64(0.132)与 UXM(1.112)**同一物理段进 en14**,SA 实际 IP `192.168.0.134`(非 seed 的 100.23,绑定已现场更新);Mac 用 en14 三别名(0.3/1.100/100.100)覆盖。适配器枚举名会漂(en3/en4→en14),文档别硬编码接口名。
