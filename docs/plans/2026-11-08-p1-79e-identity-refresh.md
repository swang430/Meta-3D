# P1-79E：Aerotech 身份取证增量

2026-11-08；基线 `c29840bf`。本次仅资料复核，没有连接转台、发送命令、修改驱动或运行HOME。
原[2026-09-22裁决](2026-09-22-p1-79e-aerotech-identity-research.md)保留历史；以下新证据替代“本次取得资料没有ASCII固件命令”的现时理解，但尚不能解除完整身份阻塞。

## 新取得的厂商原文

官网[Manuals & Help Files](https://www.aerotech.com/resources/manuals-help-files/)的Ensemble Help当前指向[帮助包](https://www.aerotech.com/wp-content/uploads/2026/07/EnsembleSoftwareHelpFiles-1.zip)。本次下载并解出CHM正文，未把厂商包上传仓库。

ZIP SHA256：`5b12b7e500a3f821217b570df971f6180a45a0f1bf076e30b1b25e8b35adc1c2`。成员包含 `Ensemble.chm`、`EnsembleC.chm`、`EnsembleLibDoc.chm`、`EnsembleProgramming.chm`、`LabViewHelp.chm`；本次解读前者与Programming。下载URL日期、版权年和示例版本均不是现场固件版本，也不据此命名整包版本。

| Ensemble.chm内定位 | 原文事实 | 适用边界 |
|---|---|---|
| `Commands/VERSION_Command.html`，Programming > AeroBasic > Commands and Functions > Status > VERSION | 命令字面量`VERSION`（无问号）；文档明确从ASCII接口打印控制器固件major/minor/patch，示例响应`%4.03.002`，含成功字符及终止符 | 已取得同系列ASCII固件读取依据；未取得现场实际版本及最低支持版本，不把示例值写为真实版本 |
| `ASCII_Command_Interface.htm`，Commands Supported over ASCII / Command Sequence | 支持表明确列VERSION；成功响应由成功字符、数据、终止符构成，字符由对应参数配置 | 不能假定所有现场都用默认字符；本文不是连机操作授权 |
| `Commands/DRIVEINFO_Function.html`，Status > DRIVEINFO | 读取axis上的drive info；`DRIVEINFO_DriveTypeID`返回区分CP/HPe/Epaq等的ID；参数是item number，常量使用涉及include文件 | 该页没有给出可直接采用的数值映射；ASCII支持表未列DRIVEINFO，不能据一般AeroBasic函数存在就拼成raw TCP查询，更不能把drive type直接当controller model |

以上三页SHA256依次：

- `f6ae72e1e2b0824db1932a8c9a78f5203d5d50dd27638a258623eeb2f918dff9`
- `3ec603ce5e32b416a887f50eea2c89ebfca043fc82a74d794681bd16310de01d`
- `490c256fb0fe491a50244b532cf6ad8d8ff40be05496c02b220c0b816d740a5f`

NotebookLM本次列出的笔记本标题中未找到Aerotech/Ensemble专题，未把UXM笔记本拿来回答。直接厂商原文是本片依据。

## 仍不能跨越的边界

官网[ASCII接口说明](https://knowledgebase.aerotech.com/spaces/AKB/pages/58524063/Configure%2Bthe%2BASCII%2BCommand%2BInterface)区分A3200与Ensemble/Soloist配置。后者端口来自所选Socket参数；不能把A3200默认8000当作所有型号的身份依据。仓内集成说明的8000只是既有接入配置。

[迁移表](https://help.aerotech.com/automation1/Content/AeroScript-Equivalents-of-AeroBasic-Ens-Sol.htm)仍只是DRIVEINFO到DriveGetItem的映射；[Automation1身份函数](https://help.aerotech.com/automation1/Content/Concepts/Controller-Information-Functions.htm)不能替代Ensemble协议。这些官网页面本次已重新读取。

`RealAerotechDriver.capture_evidence_environment()` 当前仍返回 `model=None` / `firmware_version=None`；不凭帮助包、IP、配置名称或示例响应补真。
本次资料复核完成，**P1-79E仍为Hardware/Vendor-Protocol Blocked**：固件读取已有新候选依据，完整型号身份及现场适用性未齐，不进入HAL实现，也不改正式位置证据的unknown。

## 下一次需要的最小证据

1. 从现场既有配置界面/资产记录取得控制器、drive、固件及ASCII接口配置的可追溯信息，供厂商匹配；该人工材料本身不替代正式live identity。
2. 厂商确认VERSION覆盖该版本、只读行为及响应/失败形式；不得尝试加问号或换别的命令拼写。
3. 厂商提供同一ASCII/TCP会话的model读取recipe；若依赖DriveTypeID，给出允许的ASCII表达式、数值item、返回ID映射及drive与controller的身份关系。
4. 资料齐全后另片设计缓存失效、拒绝/空回/解析失败与重连行为；厂商若只给SDK方案，仍需独立架构批准，不在本片新建Windows采集器。

这是待答清单，未发送厂商消息，未新增硬件动作。原文目录搜索没找到足够的型号recipe不等于断言全产品不支持。

## 验证

纯资料档：实际下载、解包、核对原文路径和摘要；核当前驱动、roadmap状态与链接，diff检查。未跑后端全量或现场测试，不用本地模拟冒充身份实证。
