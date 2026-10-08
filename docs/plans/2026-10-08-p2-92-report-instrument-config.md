# P2-92：报告独立测试仪器配置章节

用户批准连续队列 P2-91→P2-92→P2-93，上一片 #518 已合并为 6c6cd999；本片唯一 WIP。

可观察故障：报告只有 UUID 与步骤 JSON，不能直观看到同次执行的仪器型号、连接地址和路由。

全集与来源：BaseStation 由 validate_frozen_compatibility_snapshot 验证的冻结 resolved_binding/manifest/expected_transport；ChannelEmulator 由 validate_frozen_channel_emulator_binding 验证的冻结件；转台仅消费其冻结坐标 profile，不根据 driver 名猜型号；rfSwitch 无统一冻结配置则显式历史未记录。路由只读同次冻结 profile，信道文件复用已有 report_traceability.channel_asset。全部白名单输出，不复制凭据/任意 params，不查当前 TestCase、仪器目录或活动 HAL。冻结请求不代表实测确认，Mock 标明模拟。

实现顺序：先补报告内容与默认/自定义模板实际 PDF 的 RED；最小添加只读投影，默认及自定义模板固定保留独立仪器章节；验证篡改/缺失冻结件、Mock、敏感字段和当前配置漂移不能补真。随后相关报告/可信性链测试、PDF 渲染、compileall/diff-check与独立内审。API content 为现有字典，schema/SCPI/正式判据不变。R1→R2 最新 HEAD 无 P1 即合并同步清理，进入 P2-93。
