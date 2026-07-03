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

- [ ] **清点**:人在 F64 前核对 `D:\Scenario Packs\...` 与 `D:\User Emulations\` 下真实文件名
      (SCPI 无 MMEM、FTP 未启,只能现场看)
- [ ] **选定**:候选首选 `D:\Scenario Packs\F9815064A TS 5G FR1 MIMO OTA\1.1\`
      `3GPP_FR1_OTA_CDLC_UMa_3600M.wiz\3GPP_FR1_OTA_CDLC_UMa_3600M.smu`
      (2026-05-27 真机 load/run 100% 实测;CDL-C UMa 3600 MHz = n78/ARFCN 640000)
- [ ] **合拍验证**:DUT 在该文件加载下 attach 稳定 + 吞吐非零(= 频段/带宽/层数与终端能力匹配)
- [ ] **登记受控**(缺一不算"我们能控制"):
  - [ ] ChannelAsset「F64 N78 场景文件」的关联文件路径 = 真实选定路径(出发前已预置为上述候选,若现场换文件在信道工作台改)
  - [ ] `scd_config` 身份与文件实际参数一致(arfcn 640000 / BW100 / CDLC / UMa / 4x4 / DP)
  - [ ] 仪器抽屉 `available_channel_models` 清单更新为真实文件名(现在还是 3 个 demo 名,顺手清)
- [ ] **一致性网实证**:故意把一次会话频率设 3.5 GHz 跑一发,确认 P2-11 网真的拦(可选,30 秒,给"网在工作"留证据)

## 机动任务(非阻塞,有空隙才做)

| 状态 | 任务 | 备注 |
|---|---|---|
| [ ] | 执行队列 ~99 条 5 月僵尸清理 | 需 Simon 拍板;`DELETE /api/v1/test-plans/queue/{plan_id}` 逐条 |
| [ ] | DUTProfile + SIMProfile 建档(真 DUT/SIM 到手后) | 建好后脚本注入 `dut_profile_id`/`sim_profile_id` 可活验三层能力/防插错网;首测不阻塞 |
| [ ] | 机器重启过则:`export CHANNEL_ENGINE_PATH=~/Tools/ChannelEgine` 再跑 `start_all_services.sh` | GCM 路不依赖 :8001,ASC 路要 |

## 当日 discovered(现场只记不修)

- (空 — 现场往下加行:`[discovered on-site 2026-07-03 during 任务N] 一句话`)
