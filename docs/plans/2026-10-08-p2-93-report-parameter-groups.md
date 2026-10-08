# P2-93：独立参数与生效值章节

用户批准连续队列最后一片；base bb9734f3（P2-92 #519 已合并、main同步清理），唯一 WIP。

可观察故障：报告有冻结参数，但英文路径/嵌套JSON藏在步骤配置，无法查明系统补齐了什么、是否真正生效。

全集：复用 report_traceability 已校验的 parameters/source/application_fields/window统计与信道来源；不查询当前 TestCase/HAL/目录，不改变freeze或可信性判据。投影为载波、MAC、功率、测量窗口、方位、信道、判据、其他/历史兼容分组，中文标签/单位/请求/来源/生效值/未确认原因齐全。70个现有字段与LTE专属字段均列全；允许未来未知路径显示原审计路径，不丢字段。保存来源不是人工输入证明，默认不是实测确认。

正式生效值仅消费现有application_fields的confirmed+非模拟、对应字段requested一致的值；无逐字段回执不根据operation成功推断。统计计数标明冻结单位，不换算墙钟时间。旧measurement_duration_s/sample_interval_ms和弃用理论比率字段明确不参与当前测量/判据，不重写历史结论。长方位每16项拆行；历史没有参数显示不可追溯。

步骤：默认/自定义实际PDF与GUI step_configs同源中文值先RED；最小投影与必留PDF章节；Mock/缺失/默认来源/已确认或不匹配回执/长方位测试GREEN；相关报告与rule gates、真实PDF页面、compileall、单一Alembic head、diff-check、独立内审；稳定版全量一次。Ready PR，R1→R2，最新HEAD无P1立即合并同步清理。本轮只显示应用层schema已定义单位，无新增仪器语义，NotebookLM/SCPI不适用。
