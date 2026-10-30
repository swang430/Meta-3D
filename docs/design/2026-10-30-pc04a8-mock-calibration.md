# PC-04A-8 全Mock数值校准与32路演练

状态：用户已确认设计及一个PR交付，Task1–3本地实现并通过独立任务审查，Task4已执行synthetic32真实API/浏览器对账与唯一全后端（3个历史门失败保留）；仍待Task4/累计独立审查及PR外审。统计、原图422/参考缺项及未验边界见[验证摘要](../validation/2026-10-30-pc04a8-mock-calibration.md)。尚未PR、未部署，不授正式校准资格。优先级P1，WIP=1。

## 可观察问题

2026-10-30隔离演练使用PA副本f5883b11-f7ae-462c-acb1-a42062e51711的r6只读快照，120节点122边。生产route-calibration-paths在进入32条下行路径前返回422：正常模式包含link_antenna到baseStation.UL1的上行边，link_antenna保存类型为reference_antenna，route_calibration.py的全模式参考节点禁入条件误挡整个图。失败证据保存在本机/tmp/pc04a5d-BVAwTu，不作为远程可下载资产。

现有fixed_route_acquisition.py纯Mock分支生成同源命令预览后以simulated返回，不产生samples/net_loss_db。该行为保护正式结果，但不足以验证数值计算、逐路完整性及历史展示。

## 选择的方案

扩展现有单路和批校准，不新增校准引擎或独立执行队列。显式模拟样本优于随机自动生成：输入可复现、预期输出可独立计算。首版不提供按损耗反推样本的自动生成器，不接受客户端把expected_loss作为计算结果。

### 路径识别

校准针对已选择CE→probe下行路径及其独立参考路径核验。无关上行边不能仅因器件类型而阻断下行集合；所选实际下行路径穿过reference_antenna/receive_cable/signal_analyzer/air_path仍拒绝。显式路径引用、端口方向、内部通路、物理输出唯一性、参考路径有效性及正常/参考隔离规则保持。

不得通过删除原上行边、改用户器件类型、全局忽略参考节点或硬编码节点ID解决。对当前图继续暴露的缺声明必须如实记录，不能默认补真以凑32路通过。

### 输入与计算

单路请求增加可选的明确模拟输入；批输入按chain_id和frequency_mhz唯一关联，每一被选组合必须完整提供，拒绝重复、额外项、缺项、非法数值和样本数不符。每个样本含source_before_dbm、received_dbm、source_after_dbm；接收线缆损耗和来源沿现有逐频请求。允许可选expected_loss_db，仅用于显示计算差异，不当实测或PASS判据。

复用当前计算：每个样本Lnet=(Pbefore+Pafter)/2-(Preceived+Lrx)，对逐样本损耗求均值及样本标准差。正损耗、负增益、已知0和未知必须区分。缺接收线缆值/来源不计算损耗、不填0。模拟输入不增加PA标称增益或其它重复补偿。

客户端输入不能携带实测身份、资格或可信时间。服务器冻结输入和来源，样本时间仅为演练处理时间，不冒充硬件采样时间。未提供模拟输入时保留原命令预览兼容行为，不自动生成数值。

### 服务端安全与结果

只有服务端当前实验室绑定和实际参与驱动被权威is_mock_driver判为全Mock，才允许消费模拟输入；真实/混合/未知状态拒绝，在硬件动作前完成。单路、批预览/启动及每项实际执行均覆盖，不能只靠界面隐藏。继续复用租约、busy、取消、幂等键和最终化，不改真实停发判据。

模拟结果保持simulated与formal_eligible=false，并显式保存模拟输入来源。数值仅属模拟演练；cleanup_confirmed与真实释放未知不能补true。模拟输入来源即使状态被篡改，也不得经读取、采用预览、确认采用、冻结、报告或导出升级为真实。旧无模拟输入的记录保持原样，不批量迁移或补数。

### 界面与批量录入

复用RouteCalibrationPanel和RouteBatchPanel：提供明确“模拟演练样本”输入及批量粘贴CSV入口，按通路ID/频率映射，导入后先显示逐项校验与预览再显式启动。每样本一行，字段为chain_id、frequency_mhz、sample_index、source_before_dbm、received_dbm、source_after_dbm、receive_cable_loss_db、receive_cable_source及可选expected_loss_db；同组公共值不得冲突。

结果显示模拟样本、净损耗、标准差及可选预期差值；列表/详情/历史/演练导出始终显著标记模拟，不能仅依靠颜色。提供演练数据CSV导出，不新增正式报告或证书。dirty、busy、未知结果、跨对象迟到响应继续沿现有保护；切换真实模式不静默携带模拟输入。

## 消费方全集与实现检查

实施前逐项确认：fixed_route_acquisition与route_batch请求/结果schema，单路与批API，fixed_route_jobs/route_batch_plan/route_batch_jobs，fixed_route_evidence，route_calibration采用预览及确认，mimo_ota/route_calibration_freeze；所有samples/net_loss_db/sample_std_db读取方及报告/导出可达入口。

契约同步api/openapi.yaml、生成TS、手写GUI类型及labProfileService；界面RouteCalibrationPanel、RouteBatchPanel及其结果/历史组件。完整扫描结果写入实施记录，每项注明改动或无需改动理由，不能把本段名称清单当已完成审计。

## 验收与单PR交付

1. 当前r6失败形态的回归：无关上行不误挡；选中非法参考中转仍拒绝，不改图内容。
2. TDD覆盖模拟样本计算、缺失/非法/重复数据、已知0和负增益、期待值不污染输出、真实/混合拒绝、篡改来源不升级、取消与重入。
3. 在新临时SQLite导入前设置Mock环境，bootstrap后逐类别/绑定/实际HAL核全Mock。真实HTTP/API与真实浏览器验证录入、导入、预览、启动、结果、历史和导出；不伪造API响应。
4. 完整32路至少两频点、每路每频5样本，明确演练频点不代表仪器支持范围。独立离线期望表与服务器结果逐项对账，核64个组合/320个样本、无漏项串路、标准差与单次补偿。生产路径额外阻塞不得删除证据或放宽门掩盖。
5. 相关回归和GUI构建；共享后端变化在稳定最终输入执行唯一全量。独立规格质量/累计内审，单一Ready PR进行R1/R2，最新外审无P1按仓库规则收口。原用户数据前后只读校验，不自动部署。

本任务只验证软件演练逻辑，不宣称真机、校准认证、现场清理或B/HOLD通过。
