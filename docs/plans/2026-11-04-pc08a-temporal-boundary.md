# PC-08A 时域代理的正式消费边界

继承已批准整体设计PC-08与连续开发授权，基线a0d5c0e4；本片只处理temporal，不改变仪器命令、采集算法或开启新的标准PDP方法。

来源：现有rs_fsva._measure_pdp_sync的IFFT(abs(FFT(x))**2)实现与已保存记录；NotebookLM查询3271735c-46e8-4f27-b7c4-fab6d1211384实际返回，但所引为二级研究材料，不能据此声称标准/手册批准。PROPSIM原手册另查。
范围：去掉代理/模拟/历史无方法证据的正式PDP判词；保留原始记录供诊断审计，正式字段不冒充可比量。
不做：不改SCPI、不创造参考序列/独立参考资格，不改写旧记录，不将时域代理升级为标准PDP。其他信道方法不扩改。
验收：新采集、详情/最新/历史/状态、会话完成、编排汇总、校准报告生成/下载均不能把temporal代理计为PASS或正式KPI。

## 全集与方案

现有TemporalChannelCalibration唯一写方为ChannelCalibrationService.run_temporal_calibration；真路径调用measure_pdp，模拟路径generate_mock_pdp。现有记录无独立方法/参考资格字段。2026-11-04只读运行库SQL按validation_pass/status分组返回零行；不以JSON形状否定真实历史。

优先去掉正式比较与有效资格：新结果validation_pass/rms_error_percent/cluster_count_match=None,status=unknown,valid_until=None；原数组和工程计算保留在诊断材料。用现有JSON附方法/模拟来源声明，无迁移。未知驱动仅未验证方法，不能依据real请求推定真实来源。

读取统一投影：详情/最新的正式PDP数组为空，正式计算字段None；新增diagnostic_data包含原保存数组/计算/当时判词与方法标记，明确非正式。旧无方法为unknown，不补当前驱动。历史筛选通过/失败均排除temporal，状态未知无到期；会话统计排除temporal且有记录/请求时总判决UNKNOWN。编排结果使用UNKNOWN而非把None格式成FAIL。

报告在原报告生成器同一消费点排除temporal正式数值/判词/分母；存在或请求temporal时undetermined计数，不能让其他项100%盖过未知项。沿用现有provenance sidecar加temporal处理标识，旧无标识报告不得作为已处理正式下载；原文件不修改，提示重新生成诊断结果。

GUI、API/schema/YAML/生成TS同改，新诊断字段可查看，时域名称明确代理/非正式。消费枚举包括channel_calibration_service、api/channel_calibration、calibration_orchestrator、calibration_report_generator、api/calibration_report、pdf模板、channelCalibrationService/types/page/dashboard。

## 验证

共享正式判定/响应档：真实序列化正反例、旧记录不变、混合会话/报告未知、下载旧sidecar拒绝、实际算法双径反例（不把自相关当独立参考），相关回归、核心逆变异、四镜像/build/浏览器、稳定版本全后端。独立内审后同PR R1/R2，SHA约束合并。用户服务/库不部署。本片不关闭独立参考资料及PC-08B。

## NotebookLM 实证

2026-11-04 nlm CLI实际查询成功。PROPSIM notebook 982222b7-4953-46cd-9949-00fa97882353，conversation f7dcb528-36df-42c1-bac4-635502e3e65f：Channel Studio GCM User Guide §17描述PDP为时延色散与频率选择性；Runtime Emulation §2.1描述每个RTC环境由给定PDP定义。未找到外部独立测量参考要求，不能据此授予现有IQ后处理标准PDP资格。原输出/tmp/pc08-propsim-evidence.json。MCP插件模块加载失败，CLI替代查询成功；不将工具故障当手册否定。

## 内审与实施收窄

计划内审F1补所有会话API返回及综合报告session元数据投影；F2复用采集前register_requested_calibration_type；F3无筛选历史/最近记录的误差和判词也置空，诊断字段保留原值。实现内审F1对任意JSON请求范围先收窄列表，F2使用is_mock_driver读取真实绑定模拟来源。浏览器发现原场景覆盖条固定50%，删除无依据覆盖展示，保留未知说明。均属于同一temporal资格故障，不扩新方法。

## 验证进展

- 实际RED：隔离SQLite/mock，新增三条核心测试3 failed/56 warnings/2.35s，/tmp/pc08-red.log；均是错误正式判词，不以存在性代替行为。
- 最终相关：api-service目录 DATABASE_URL=sqlite:////tmp/pc08-related-final3.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_pc08a_temporal_boundary.py tests/test_p1_70_channel_validation.py tests/test_calibration_report.py tests/test_p1_64_quiet_zone_evidence_truth.py -q --color=no --log-cli-level=WARNING；112 passed/157 warnings/10.66s，exit0，/tmp/pc08-related-final3.log。中间旧QZ陪测换为Doppler；新测试补created_by/正确Mock类构造及reference_spectrum，不隐去初始失败。
- 生产路径Mock回归复现25ns采样下寻峰distance=int(20/25)=0的ValueError；参数下界改max(1,...)，不改采集算法或SCPI。
- 逆变异仅将新temporal validation_pass=None恢复True，test_mock_capture_is_diagnostic_and_cannot_pass实际1 failed/40 warnings/0.15s；finally比较原文并恢复。/tmp/pc08-mutation.log。
- GUI生成契约及build通过；最终built in21.75s，/tmp/pc08-build-final.log。真实浏览器操作实际ChannelCalibrationPage，HTTP边界隔离替身：历史UNKNOWN、诊断弹窗保留旧true但非正式警示、采集完成黄提示。截图output/playwright/pc08-method/diagnostic.png与completed.png；临时入口已移出仓库，独立5179服务与浏览器关闭。后端真实HTTP由相关测试独立覆盖，不称浏览器使用真实API。
- 实际生产PDF生成器读取隔离旧PASS记录，/tmp/pc08-diagnostic.pdf的摘要/明细UNKNOWN、正式RMS误差为空；末页渲染/tmp/pc08-diagnostic-page.png已检查。临时验证脚本首次模块导入顺序引发既有循环导入，按应用入口初始化后生成成功，无生产绕过。
- 冻结输入全量：api-service目录 `DATABASE_URL=sqlite:////tmp/pc08-full-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests -q --color=no --log-cli-level=WARNING --log-level=WARNING`，**11 failed / 8576 passed / 17 skipped / 11241 warnings / 1220.46s**，exit1，非全绿。日志`/tmp/pc08-full-final.log` SHA256 `6e91a3dc679c6e0d2f9b73f036192889398e2357577d33216a2be2fea6c04e09`。启动后至结束1357项非docs输入hash未变（快照在启动后创建，之间没有编辑输入）；期间仅编辑本计划/roadmap，不声称全仓所有文件未变。
- 四条失败是本片正式判词变化后的旧预期：test_channel_calibration::test_run_temporal_calibration、test_e2e_calibration的quick_validation_workflow及calibration_service_direct、test_workflow_engine::test_run_channel_calibration_step。仅适配这三个测试文件，保留数据生成、落库、工作流完成和报告生成；计数按Doppler/spatial实际布尔判词核对，含temporal总判词None。
- 上述适配后稳定输入整文件回归：api-service目录 `DATABASE_URL=sqlite:////tmp/pc08-adapted-final.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_channel_calibration.py tests/test_e2e_calibration.py tests/test_workflow_engine.py tests/test_pc08a_temporal_boundary.py -q --color=no --log-cli-level=WARNING`，**97 passed / 342 warnings / 12.40s**，exit0，`/tmp/pc08-adapted-final.log`。首次适配脚本assert停下但后续shell仍启动旧测试，其输出不作最终证据；修正限定到目标函数后重跑。生产/契约未改，按影响面组合原全量与此回归，不称最终提交全量全绿。
- 六项基线失败与#556～560相同：pc04a2_gui_contract、pc04a4a_nominal_properties、pc06a1_batch_api、pc_04a_fixed_route_api四条契约同构，以及G8/G11两条历史文档路由门。基线逐项同红依据见[撤销片验证记录](2026-11-04-pc05a-revocation.md)。
- 额外拓扑`test_changed_pair_invalidates_old_request_and_batch_preview_and_mock_reenters[normal]`在全量中报实验室不存在/停用，不能归为六项基线。当前独立参数两例2 passed/59 warnings/7.51s；未改主目录7f5bb56b同样2 passed/59 warnings/7.45s，均exit0，分别`/tmp/pc08-topology-repeat.log`和`/tmp/pc08-topology-baseline.log`。相关测试、fixed_route_jobs及fixed_route_acquisition与7f5bb56b无diff；仅证明独立运行未复现，不声称已修复偶发。整模块核对结果另记。

- 拓扑整文件核对：api-service目录 `DATABASE_URL=sqlite:////tmp/pc08-topology-module.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=. .venv/bin/python -m pytest tests/test_pc04a4c_internal_routes.py -q --color=no --log-cli-level=WARNING`，68 passed/643 warnings/62.42s，exit0；`/tmp/pc08-topology-module.log`。偶发根因未明，不放宽断言、不加重试。本片生产改动不涉及该作业路径。
- 文档最终G8/G11定向复核：根目录 `DATABASE_URL=sqlite:////tmp/pc08-doc-gates.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=api-service api-service/.venv/bin/python -m pytest api-service/tests/test_rule_gates.py -k 'g8_docs or g11_docs' -q --color=no`，2 failed/68 deselected/39 warnings/1.62s，exit1，仍为上述历史文档路由失败，`/tmp/pc08-doc-gates.log`。
- 独立累计内审及三文件测试增量审查CLEAN。全量后输入差异仅三个旧测试文件；生产、契约、依赖未变化。以上组合证据为提交验证依据，不将六项基线或未复现偶发洗成通过。
