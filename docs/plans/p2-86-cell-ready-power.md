# P2-86 Cell-ready 功率测量实施计划

用户批准 A 方案：Cell ON 后不再用 latest result 证明本窗口测量成功。

## 取证与边界

NotebookLM query `d94a6d5b384d`，notebook `982222b7-4953-46cd-9949-00fa97882353`。
已核仓内 Propsim User Reference Rev 10.2：§20.4.4.6 印刷 p250，
`INPut:LEVel:MEASure?` 返回平均电平和 crest；测量失败（无输入或输出过强）产生设备错误。
§20.4.4.36 p258 的 GET 只是 latest result，不证明当前信号存在。
NotebookLM 返回的页码不一致，以 PDF 原文为准；不采纳其超出原文的支持范围推断。
本片复用既有 1.0 秒测量及错误队列，不新增 SCPI、阈值、RSRP 或正式 provenance。
成功只表示测量已确认，不表示 LTE 有效；设备拒绝不能直接等同无信号。

## 顺序实施

1. 驱动 RED：有限旧数值伴随设备错误、缺 crest、非有限值必须拒绝；GREEN 将测量与错误队列绑定同一锁窗口。
2. 观察 RED：旧结果有限但新测量失败时 strict 拒绝、非 strict 警告；GREEN 按活动输入口测量。
3. 执行 RED：未确认的观察不能升级手动输入验证；GREEN 复用 operation recorder 绑定 execution/lease/instrument。
4. 回归驱动、观察、手动输入、operation receipt、规则门及全后端；compileall、Alembic head、diff-check。
5. 独立只读功能内审；Ready PR；Codex R1→R2，最新 HEAD 无 P1 方可合并、同步与清理。

## 路径全集

- F64 measure_input：输入控制器、P08 诊断、MEASURE 手动输入；均已有 None 失败分支。
- Cell-ready：观察服务 → MEASURE 回调 → measurements.attach_power_observation → 手动输入验证。
- 证据：既有 channel_emulator_operation_receipt 和 F64 measure_input 投影。
- 不重算历史执行、不改 GUI/API 类型（measurements 为既有 JSON）、不连接真机、不重启用户服务。

现场仍须验证 F8800A 固件 8.0 的设备错误行为；本地测试不代替硬件证据。
