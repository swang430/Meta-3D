# P2-71：F64 文件常态化提供与版本控制调研结论

**日期**：2026-09-13。**性质**：资料与现有现场记录核对；本次没有连接、查询或写入真实 F64。实施步骤见[调研计划](2026-09-13-p2-71-f64-file-provisioning-plan.md)。

## 1. 裁决

当前 CAICT F8800A **不能据通用手册直接上线自动文件发布**。PROPSIM User Reference Rev 10.2 确实列出 `MMEMory` 文件列举、传输、取回、删除及 `MEM` 预加载/当前名称等命令；但 2026-05-13 CAICT 现场记录的是 `MMEM:CDIR?`、`MMEM:CAT?` 返回 `-100,"ATE command not supported"`，FTP 21 端口关闭。两种证据并不矛盾：前者描述手册命令面，后者描述**这台机器当时的可用面**；固件/配置差异的原因尚未证实，不能猜成“升级固件即可”。不能把 FS16 的可用 `MMEM` 或通用 Keysight 命令面移植到 F64。

本片的可执行决定是**维持现有仪器侧 Windows `.smu` 路径由操作员预先提供**，正式执行继续消费冻结的 ChannelAsset（适用 vendor-file 路径时）与现有 `CALC:FILT:FILE` 加载、状态、错误队列、operation receipt 和生命周期证据。完整执行链可证明“同次在此仪器上加载、运行了该路径所指的可解析仿真”，**不证明设备磁盘字节等于离线源文件的 SHA-256 或没有被同路径覆盖**。不增加新的正式设备字节证明、自动上传、自动目录扫描、自动替换或 Readiness/MEASURE 前置；SMB `smu-scan/smu-sync` 仍仅是开发/调试离线导入工具。

**交付界限**：P2-71 的“手册 × 现场记录 × 软件现状”研究和路线裁决可非现场完成；设备侧可重复发布、字节验约和回滚的真机验收仍是 hardware blocker，不因本文件或本地测试关闭。没有设备字节证明时，报告不得声称已验证设备侧文件版本。

## 2. 证据等级与原厂出处

以下“手册列出”**不是**“当前 CAICT 仪器支持”。原厂资料均为仓内原件：

- [PROPSIM User Reference Rev 10.2（2024-09-16）](<../../Instrument_API_Doc/Keysight PromSim F64/Propsim User Reference.pdf>)：§20.4.3.1（印刷页 240）、§20.4.13.1–7（315–317）、§20.4.14.1–7（317–318）。
- [PROPSIM ATE Environment and Practices AN Rev 2.2（2021-06-29）](<../../Instrument_API_Doc/Keysight PromSim F64/Propsim ATE environment and practices AN.pdf>)：§1.1（页 5）、§2.2.1–4（页 12–13）。
- [PROPSIM F64 Quick Guide Rev 3.4（2024-04-25）](<../../Instrument_API_Doc/Keysight PromSim F64/PROPSIM F64 Quick Guide.pdf>)：§3.2 System 菜单，`Windows File Manager` 与 `Unplug or Eject Device`。
- [CAICT 2026-05-13 现场团队简报](../site-debug/2026-05-13-summary.md) §2、§6，[现场 playbook](../site-debug/2026-05-27-onsite-playbook.md) §1：这是**历史现场记录**，并非本次重测；[F64 清单测试](../../api-service/tests/test_f64_channel_model_listing.py) 文件头也记录了两条 MMEM 查询的 `-100`。NotebookLM 的“PROPSIM 资料”本次只用来定位章节；以下肯定结论已回到 PDF 原文核对，未采纳其无原文支撑的文件锁定推断。

| 能力/手段 | 手册边界 | CAICT 该机/当前实现 | 本片结论 |
|---|---|---|---|
| 本地文件与备份 | ATE AN §2.2.1.1 推荐 `D:\User Emulations\`，并提示校准/换盘时备份；Quick Guide §3.2 有 Windows File Manager、USB 安全移除菜单 | 既有 GCM 路径从仪器本地 `D:` 加载；未重验设备侧版本 | 可以维持**人工预置**，但文件管理动作、可逆备份和实际字节对账需现场制度与证据 |
| 远程存放 | ATE AN §2.2.1.2 提到企业共享、NAS 或可移动介质，可让多台设备共用文件 | 本项目只证实过开发用 SMB 只读副本；未证实适合正式发布、原子替换或执行期同字节 | 不把网络共享/SMB 纳入正式执行或当作设备证明 |
| `MMEM:CAT?`、`MMEM:CDIR[?]` | User Reference §20.4.13.1–3：当前目录、文件名/类型/字节数及目录切换 | 现场记录 `CDIR?`、`CAT?` 均 `-100`；生产目录来自操作员清单而非实时 SCPI | 手册有，**当前该机不可用记录**；不自动扫描，不用文件大小代替内容身份 |
| `MMEM:DATA` / `MMEM:DATA?` | User Reference §20.4.13.4–5：IEEE 488.2 二进制块写文件/读文件；示例为 IQ/WFM，并未专门验 `.smu` 在 F8800A 上的可达性 | 该机没有这两条的受控真机验约；同命令族两条查询已报不支持 | 不写驱动。若未来固件实测支持，**取回完整字节并在客户端算 digest**才可能比大小/名称更强；这只是候选方案，不是现有设备侧证明 |
| `MMEM:DEL`、`MMEM:MDIR` | User Reference §20.4.13.6–7：删除文件、建目录 | 未经当前设备验证；写/删可破坏运行资产 | 不试探、不实现；先有独占、安全空闲、备份和恢复证明 |
| `MMEM:LOAD`、`MEM:ALL?`、`MEM:CURRENT?`、`MEM:FILE:SIZE?` | User Reference §20.4.14：分别为预加载到**内存**、列表/当前名称/仿真大小（MB），并非磁盘内容 hash；`MEM:DEL:*` 仅在全部 emulation 关闭时使用 | 当前设备未验；生产路径未消费这些查询 | 不能用内存名称、仿真大小或预加载响应冒充磁盘字节版本 |
| `CALC:FILT:FILE` | User Reference §20.4.3.1：打开给定文件；ATE AN §2.2.3–4：大文件须延长超时，`*OPC?` 后读响应和错误队列 | 当前驱动在 CLOSE/STATE、FILE/OPC、错误队列、状态/频率/拓扑回读后生成同次 operation receipt | 保留为**加载/运行证据**，不提升为内容 digest；`*OPC?=1` 单独不能证明成功 |
| FTP | 上述三份原厂资料没有提供适用于该机的 FTP 发布/验约协议 | CAICT 历史记录 21 端口关闭，现有 ASC/B2 FTP 代码不构成当前机器可用证明 | 不作为当前 `.smu` 常态发布路线 |

**重要的否定限定**：“所核对章节未给文件 hash/修改时间/内部版本查询”不等于断言所有型号或固件绝无此功能；本片没有穷尽其他厂商服务或软件版本。`MMEM:DATA?` 若真实可用，可**由客户端**对完整取回字节计算 hash；当前机器不能据手册直接宣称这一点。

## 3. 当前软件的真正读写链

按仓库 `AGENTS.md` §0.5 枚举同一事实的全部关键产生/消费方，避免把离线副本或缓存当设备侧真值：

| 阶段 | 当前产生方/消费方 | 所能证明与不能证明 |
|---|---|---|
| 离线导入 | `smu_project_inventory.sync_smu_project_truth` 从**API 主机挂载副本**读取字节，写 `ChannelAsset.payload.smu_project_truth.sha256/size_bytes/instrument_path` | 证明扫描时那个副本；不能证明 F64 磁盘字节。`smu-scan/smu-sync` 为显式开发工具 |
| 资产登记 | `channel_asset_service._has_verified_smu_project_truth` 对资产路径、频率与服务端扫描字段做形态/一致性校验；`associated_file_path` 是仪器侧 Windows 路径 | “verified”仅对离线工程记录与资产字段成立，不是设备 attestation |
| 冻结 | `channel_emulator_execution_plan.freeze_channel_asset_resolution` 把 ChannelAsset id、source 与**数据库可执行内容** digest 冻结；MEASURE `validate_resolved_channel_asset_against_freeze` 拒数据库漂移 | 不读 SMB，也不读 F64 文件字节；同路径被设备侧覆盖时 digest 不变 |
| 解析与加载 | `channel_asset_resolver` / `gcm_strategy.NativeModelStrategy` 选冻结路径；`RealPropsimF64Driver._load_smu_with_preflight` 经同一 VISA session 关闭旧仿真、加载、同步、错误队列和状态/频率/拓扑回读 | 证明本次仪器接受/加载路径及可读运行状态；`get_loaded_emulation_file` 是驱动成功后记录的路径，不是独立文件字节回读 |
| 同次证据与输出 | `channel_emulator_operation_receipt` 绑定 execution、attempt、lease、instrument、asset digest；P2-66 `execution_evidence_outcome`/报告/历史消费完整证据 | 证明同次生命周期，不推出离线与设备字节相等；模拟、未知和诊断仍不能洗成正式 KPI |

因此，今天即使 `smu_project_truth.sha256`、冻结 digest、文件名、频率和加载 receipt 全相符，仍存在“设备同路径文件被后来替换”的**剩余风险**。不得把这些不同层级的 digest 合称“F64 文件版本已验证”。

## 4. 发布责任、版本身份与回滚边界

**当前保守运行形态**：由实验室操作员在维护窗口按厂商支持的本地文件管理途径预置 `.smu`，记录来源制品、来源 hash、目标 F64 的型号/序号/固件、绝对 Windows 路径、发布人/时间和旧版备份位置；在现有 ChannelAsset 中登记该路径，并只用现有正式加载链检查当次可运行。来源 hash 是**离线制品身份**，不是 F64 已证明的 hash；若设备侧无法取回/核验字节，发布记录明确标 `device_bytes_unverified`，不得给 UI、报告或资格链新的绿色字段。

**未来制品候选**：内容不可变的 `.smu` release 包 + 同包 manifest（源文件 SHA-256、字节数、模型/频率/拓扑元数据、适用 F64 型号/固件、目标绝对路径）。这是待实现的设计，不是本 PR 新增数据真值。推荐新版本用**新路径**并先保留旧文件，避免同路径原地覆盖导致冻结路径仍相同却加载不同字节；路径切换也必须在没有活动 execution/lease、F64 可确认安全空闲时做。不能仅凭文件名、大小、`MEM:CURRENT?` 或手工确认把正式 device-byte trust 升级。

**回滚候选**：维护窗口保留上一份经独立核验的设备侧文件及其资产登记；新版本验证失败时先保证 RF SAFE_IDLE/关闭仿真，再重新选择旧路径并以既有 SCPI 加载/状态/错误队列确认可运行。若旧文件是否仍在设备上未知，回滚**失败并隔离**，不能把旧数据库路径当回滚成功。手册 `MEM:DEL:*` 是内存清理而非磁盘回滚，`MMEM:DEL` 是破坏性删除，均不在本片自动调用。

## 5. 现场门与下一片准入条件

1. **能力分类复核**：在排除活动执行/其他 ATE client、由操作员安排独占维护窗口后，可复用已登记的 `propsim_f64_health` 观察 `MMEM_CDIR`、`MMEM_CAT` 的 `SUPPORTED`/`UNSUPPORTED` 分类。它会先发送 `*CLS` 并逐项消耗 `SYST:ERR?`，不保留 MMEM 查询原始回复；运行前须保全既有错误证据，不得在执行期间或尚待诊断的会话里运行。若分类仍为 `-100`/不支持，就停止 MMEM 路线；若显示支持，也只能进入下一道受控原始回复捕获设计，**不能**把 health 分类当目录内容或设备版本证明。
2. **原始回复与文件读写准入**：先设计能安全记录查询原始回复及错误队列的 checked-in 诊断载体；要取回或发布，还须获得当前型号/固件对 `MMEM:DATA[?]` 的厂商适用依据、安全独占/空闲条件、文件大小上限/超时与完整二进制块处理策略。不得在正式 TestCase、临时脚本或通用 health 序列里盲试写/删。
3. **设备字节准入**：在已知测试文件上实证“源 digest → 安全发布 → 设备完整取回 digest → 再次加载 → 替换/异常/回滚”的原始往返与故障路径；若仍无法取回完整字节，则保留人工 provision/`device_bytes_unverified`，不得引入自动正式验约。读回即便成功，也要证明与**本次冻结、同一设备、同一路径/时刻**绑定，不能用前一天的读回给今天执行背书。
4. **并发/安全**：ATE AN §1.1 说明 UI 与远程操作有模式/打开文件约束，F64 Release 2 起可切换 Local/Remote；现有 HAL 的 execution/lease guard、Remote→Local 交还、SAFE_IDLE 和 `teardown_unconfirmed` 门不可绕过。手册未说明运行中原地覆盖的安全语义，因此不得试验原地覆盖。失败或取消时优先保留旧设备会话与旧文件，禁止“上传失败但路径已切换”。

**下一步性质**：这是 P2-71 的硬件/部署资格待验，不是本次非现场代码完成证明。即使未来 MMEM 查询在另一台或升级后的机器可用，也要给该**具体设备+固件**独立认证；不能扩大现有生产 HAL 的正式能力白名单。
