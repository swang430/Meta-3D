# 现场执行计划 — 2026-07-21 CAICT(P0-5 attach 正式注册 → ★四方位吞吐)

> 上承 [onsite-tasks-20260703.md](onsite-tasks-20260703.md)(收工总结 + discovered 全录)。
> 铁律不变:现场不写 driver 代码 / SCPI 探测 > GUI > RDP / 单 gate 卡 >半天就停 /
> software 异常 = 记 discovered 不当场修。
> 状态列现场随手改:`[ ]` 待办 / `[~]` 进行中 / `[x]` 完成 / `[!]` 卡住(记原因)。

## 0. 目标(与 07-03 的差量)

07-03 走到 attach 差一步(DUT 已见 **-96 dBm RSRP**,直通链路终验通过)。今天只剩两个 gate:

1. **P0-5 DUT attach 正式注册**(记真实 IMSI)——上次的 -96 RSRP 态直接续;
2. **★ 信道模型下 4 方位吞吐**(BW40,`onsite-run-channel-throughput.sh` 一键)。

**一次成功 =** ChannelAsset(UMa 3600M 真值 3549.99)→ F64 真加载 → DUT attach 下
4 方位测出 4 个不同吞吐值 + analysis + PDF。

## 1. 出发前已完成(2026-07-20 晚,全部落 main)

- **回家正修 #193–#213 全收口**:07-03 的 11 项现场坑 9 项已修实证(缺省不写 CENT /
  UXM OFF→配→ON 编排+回读对账 / band=None 崩溃 / HAL 互斥+超时排水 / 转台 move 前懒重连 /
  UXM inst0 重定向 / F64 直通编排(GO 前无条件 STATIC 0)/ ARFCN fallback 636666 /
  attach 诊断序列默认基线)。**明天这 9 类坑不再需要手工绕行**。
- **BW40 拍板落地**(2026-07-20 用户拍板,跟 EMQuest n78 基线):脚本默认 `BW_MHZ=40`;
  资产 UMa_3600M 重登记 `MF_N78_636666_BW40_CDLC_UMa_4x4_DP_v1`(scd/顶层 bw=40);
  其余 17 条保持 100(各自基线待实测)。
- **UXM BW 幂等**(新):`set_cell_config` 预读当前 BW,相同则免写免 OFF→ON 环绕 →
  **attach 后跑 run 小区不重启、DUT 不掉线**(07-03 后暴露的最大序列雷已排)。
- **DL 功率守护**(新):脚本注入 `target_tx_power_dbm=-46`(`TX_POWER_DBM` 可覆盖)——
  堵住 schema 默认 0.0 冲掉 EMQuest -46 基线的雷。
- **方位角环境变量化**(新):`AZIMUTHS=0,90,180,270` 默认;转台异常退化 = 单方位×4 次。
- **mock 彩排 PASS**(2026-07-20 晚):新默认值(BW40/-46/636666)端到端全 5 相位
  completed,engine=keysight_gcm,频率一致性网过,4 方位 4 值。
- 本地 DB 资产值已验证 = 真值(3549990000 / arfcn 636666 / bw 40)。

## 2. 到场 15 分钟开跑序列(主线,按序执行)

| # | 状态 | 动作 | 判据 / 备注 |
|---|---|---|---|
| 0 | [ ] | 开机自检:栈四绿(PG docker `meta3d_db` / :8000 / :5173 / :8001;重启过机先 `export CHANNEL_ENGINE_PATH=~/Tools/ChannelEgine`)+ 网络三别名(`ifconfig en14` 看 0.3/1.100/100.100) | UXM 失联先查本机别名再怀疑仪器(07-03 教训) |
| 1 | [ ] | **SCPI 冒烟**(干净 3334 会话):① STOPPED 态重复 `DIAG:SIMU:GOS` ② 无 sim open 态 `GOS` ③ 无 sim open 态 `STATIC 3`,各查 `SYST:ERR?` | GOS/STATIC benign 错误码无干净会话实证([propsim_f64.py:1433](../../api-service/app/hal/propsim_f64.py) 注释)。若报 benign 码:记 discovered,临时逃生 = attach 序列参数 `establish_f64_passthrough=false` |
| 2 | [ ] | HAL 切 Real + 重载 → 状态三查:UXM 小区(期望 **636666/BW40/-46/ON** = EMQuest 基线态)、F64(`STATIC?`/`STATE?`/工程)、F64 参考(-15/crest12,**面板核**) | UXM 若被外部改动:BW 幂等只对 BW 生效,ARFCN/功率由 run 下发对齐(ms 级即发即效) |
| 3 | [ ] | F64 直通默认态:纯净加载 UMa 工程(**勿写 CENT**,工程自带 3549.99)→ 直通稳态 = **STOPPED + STATIC 3** | 07-03 实证语义;attach 默认态 |
| 4 | [ ] | **DUT attach**(-96 RSRP 态续;慢则 UXM EPRE -46→-36 一条命令)→ **记真实 IMSI** | P0-5 gate;IMSI 供脚本 `DUT_IMSI` |
| 5 | [ ] | ★ 一键吞吐:`DUT_IMSI=<真IMSI> ./scripts/onsite-run-channel-throughput.sh`(默认已 3549990000/BW40/-46/4 方位) | run 内部自动:cell_config(BW 相同免重启,DUT 不掉线)→ F64 加载 + `STATIC 0`+GO(衰落恢复)→ 满业务闭环 AUTOSET → 4 方位吞吐。**判真伪唯一权威 = 驱动模式页 Real + 仪器面板动作**(mock 也出 4 个不同值) |
| 6 | [ ] | 收工 review 三问 + discovered 回填本文档底部 | 15 min |

**吞吐 gate(★今日成功判据)**:4 方位 4 个**不同**吞吐值 + analysis + PDF。

## 3. 风险与预案(likelihood × impact 排序)

| # | 风险 | 症状 | 预案 |
|---|---|---|---|
| ① | **忘切 Real 跑成 mock** | 数值"合理"不能判真伪 | 唯一权威 = 驱动模式页 + 面板动作;跑前照检查表核 |
| ② | 输入电平闭环不收敛(DUT 重连慢 / 无业务态) | run FAILED "Input-level closed loop did not converge" | 确认 DUT attach 稳(UXM 面板)再重跑;仍不过 → 临时 `precheck_strict_input_level=false` 降级(TestCase config PATCH)+ 手动满业务态 `INP:LEV:AUTOSET 0,3`,记 discovered |
| ③ | 转台方位 2+ 断连 | move 失败 | P1-20 懒重连已修,理论自愈;仍炸 → `AZIMUTHS=0,0,0,0` 退化跑(同方位 4 个测量窗;注意 `AZIMUTHS=0` 只测 1 次) |
| ④ | 多写方污染(EMQuest / 主控台页) | 参数漂移 / 会话串线 | **测试窗口纪律:关主控台页签 + EMQuest 不操作**;07-03 两次实证 |
| ⑤ | **P1-8 未修:mock cal cert 在 real 假过** | precheck cal_pass:true 但补偿值是 mock | **知情接受**:吞吐 smoke 不信 RSRP/绝对功率;若需绝对值,现场重跑真校准 |
| ⑥ | F64 假成功族残余(#211 已收口 11 站点) | GUI 日志面板 ERROR | 错误现在**可见**(ZoneLogsAlerts);见 ERROR 就停,按日志排查 |
| ⑦ | UXM 15min 空闲断连 / F64 会话 wedge | BrokenPipe / -200 连锁 | P1-21 已修自动排水;闲置 >10min 跑 measure 前照旧先重载 HAL(双保险) |
| ⑧ | attach 后 run 里小区意外重启(幂等失效) | UXM 面板小区 OFF→ON,DUT 掉线 | 新代码首战;若触发:① 确认 UXM 当前 BW 真是 40(幂等只认相同值),否则先手工对齐 BW 再跑;② **BW 已同仍重启** → 疑 ON 态同值写 band/duplex 触发 UXM 内部重配(真机零实证,门审 F5),从 cell_cfg 侧逐参数比对定位;记 discovered |

## 4. 机动项(非阻塞,有空隙才做)

| 状态 | 任务 | 备注 |
|---|---|---|
| [ ] | **★ 获取 F64 (F8800A) 手册**(向 Keysight/管理方要) | 根因:我们只有 FS16 手册,全部命令形式照 FS16 写(memory 2026-07-20)。拿到后确认 `CALC:FILT:CENT` / `INP:LEV:AMP` **回读**命令形式(07-03 盲试 CH?/GET? 均无应答,且一次无应答查询即连锁错位,不可再盲试) |
| [ ] | Keysight 在场则当面问:F64 ATE 配置类回读语法;`INP:MEAS:RES:GET?` 延迟应答语义的推荐读法 | 一句话可能解锁两个物理受阻项 |
| [ ] | 17 条 .smu 资产频率逐个实测(纯净加载+面板,或 SMB 读工程解析) | UMa_3600M 已证伪文件名;其余按厂商文件名存疑 |
| [ ] | DUTProfile + SIMProfile 建档(真 DUT/SIM 在手) | 建好后脚本注入可活验三层能力 |
| [ ] | 执行队列 5 月僵尸清理(~99 条) | 需 Simon 拍板;`DELETE /api/v1/test-plans/queue/{plan_id}` |
| [ ] | E1 RF2(BEAM 1-V)线缆对调判定 | 07-03 遗留:值跟线走=线/UXM 口,值跟 F64 口走=F64 口 |
| [ ] | 频率一致性网反证(故意 3.5GHz 跑一发确认拦截) | 30 秒,"网在工作"证据 |

## 5. 升级规则(贯穿全天)

单 gate 卡 >半天且非纯硬件物理问题 → 停,整理 SCPI trace 远程协作。
software 异常 = 记 discovered 不当场修(违反即停)。

## 当日 discovered(现场只记不修)

<!-- [discovered on-site 2026-07-21 during XXX] ... -->
