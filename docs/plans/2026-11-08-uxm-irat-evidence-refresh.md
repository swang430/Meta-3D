# P2-52/P2-54：UXM IRAT 资料复核

2026-11-08；基线 `fb5b1827`。交付是本次资料复核及厂商问题清单；不是IRAT能力实现或现场验收。没有连接仪器、发送查询/写入、修改生产代码或正式证据白名单。

## 已核资料

NotebookLM笔记本 `236d9621-e3ce-4ed1-a8e1-7819b674dbcd` 的六份资料，conversation `adfb5e02-4f11-450b-a91d-801d22667604`；逐条回到本机手册文本核对，不把回答推断当原文。资料目录为 `Instrument_API_Doc/Keysight UXM NR SCPI/`，本机拆分文本不随本片上传。

归档 `5G_NR_Test_Application_SCPI_Reference.zip` SHA256：`52f57d60f063026c15a9bcd374b8cd4bab79207b5e28877395a15fd7d650dbfe`；成员 `5G_NR_Test_Application_SCPI_Reference.html`。现有[首次窗口取证](2026-08-30-p2-52-uxm-window-boundary-evidence.md)仍保留历史。

| 原文定位 | 本次核到的事实 | 不能推出的结论 |
|---|---|---|
| `UXM5G_SCPI_06_General_Examples_Shared.md`，General > Miscellaneous commands，`TaGeneralTestApplicationMode` | `SYSTem:APPLication[:NAME]` 的枚举分别列NSA与LTE_NR_IRAT | NSA不是可直接等同IRAT的适用性证明 |
| 同文件，Examples > Measuring BLER；HTML `#examples-measuring-bler` | 示例提供Single、长度5000、启用测量和progress-count比较 | 示例不能证明现场IRAT/固件/选件组合，也不能单独证明清理及重复窗口隔离 |
| `UXM5G_SCPI_02_NR_PHY_Measurements.md`，NR BLER/Tput > DL Retransmit > BLER/Tput；`TaNrBlerTputBlerThroughputMeasurementMode` | Single为0、Continuous为1；Application Mode标NSA/SA | 未得到IRAT适用性证明 |
| 同章，`TaNrBlerTputBlerThroughputMeasurementLength` | 200倍数及向上取整；正文写2000..360000，Range写200..360000 | 下限存在文本冲突，不擅自选一端，更不写入IRAT |
| 同章，`TaNrBlerTputBlerThroughputReset` | 清零时进行中的测量会自动重启；No query | 清零不等于安全停止，也不凭空补查询形 |
| `UXM5G_SCPI_03_LTE.md`，LTE System > App Info，System error queue，PD1.9.1 | `SYSTem:ERRor[:NEXT]?`，空队列返回`+0,“No error”`；Application Mode为NSA/SA | 未得到IRAT适用性证明；空串与裸0不据此当空队列 |

本次在Keysight官方域检索 `"LTE_NR_IRAT" "BTHRoughput"` 与 `"LTE_NR_IRAT" "SYSTem:ERRor"` 未获结果；这是此次检索范围的结果，不是“厂商不存在资料”的断言。

## 裁决与厂商待答清单

**现有资料仍不足以解除P2-52/P2-54的IRAT资料阻塞。** 不新增写诊断，不从NSA/SA示例移植命令，不用试写代替资料。

后续需厂商提供与现场实际Test Application、固件、选件匹配的章节或签署说明，逐项回答：

1. 有限窗口Single/Length/启停命令完整形式、参数值域（解释长度下限矛盾）、前置条件和可查询字段。
2. progress-count到界是否权威完成、何时稳定、下一窗口如何确认不继承；异常/取消时如何处理。
3. IRAT错误队列的完整查询、空队列/失败响应及读取副作用。
4. cleanup/reset恢复步骤及权威完成回读，尤其避免把可能自动重启的清零当停止。
5. 上述依据覆盖的版本/选件与现场设备绑定信息。没有这些信息，资料版本不能代替设备版本。

本清单仅供索取依据，未向厂商发送消息。依据齐全后再按既有roadmap设计实现和现场载体。

## 当前软件核对与验证边界

`uxm_base_station.py` 的manifest及窗口仍为 `clear_read_only`，不能确认closed；`app/data/scpi_evidence/p0_5_commands.json` 的 `uxm.error_queue` 仍为 `unverified`。本片不将诊断排队成功提升为正式IRAT资格。
P3-21仅统一现有诊断错误处理，没有填补这里的厂商适用性缺口。

纯资料档：核对原文、归档锚点、现有生产状态、相对链接及diff；没有运行硬件或重复后端全量。正式状态只在roadmap维护。
