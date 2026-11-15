# P2-16 S5c：调用Lauraycs现有接口，接收已有聚簇结果

状态：2026-11-14用户要求恢复Lauraycs，只修改Meta-3D与ChannelEgine并推送GitHub外审。本设计按该范围替代此前修改Lauraycs导出端的方案。

## 范围与职责

Lauraycs工作区已恢复修改前的main `53ea4cf9`，无源码差异；`e094cfe7`只保留为未采用的本地备份，不部署、不再推送GitLab。
Meta-3D调用原版已有接口，ChannelEgine校验并计算采样时刻的复响应。全链不在接收端重复聚簇，不加载HyperRT。

原版接口为`POST /api/task/channel-analysis/clustering/kmeans/analyze`，接受源MPDB位置、内部链路ID、帧ID、可选接收端ID和请求簇数；返回单帧`algorithms`完整聚簇结果、身份、原始/有效路径计数，以及无路径或全部过滤的明确状态。接口已在源码核实，尚未对可运行部署作原样本验证。

## 验收关系

| 入口 | 权威读取与边界 | 消费者 | 可观察断言 |
|---|---|---|---|
| 采集清单 | 操作方明确提供样本身份与非均匀时间；不假装服务验证了清单外的全部样本 | Meta-3D逐帧HTTP调用 | 清单先完整校验，再发请求；不用FRAME_ID猜秒数 |
| 原版聚簇响应 | 回显MPDB位置、内部LINK与帧身份；输入/有效计数与算法结果一致 | Meta-3D交换文件 | 错身份、超预算、失败留为失败帧，不丢分母 |
| 完整交换文件 | 固定版本、单位、复H与时间契约 | ChannelEgine读取器 | 不改成原始rays，不再次聚簇，未知多普勒保持null |
| CE逐帧响应计算 | `Σ H exp(-j 2π Δf τ)`，时延ns转s | 离线核对命令 | 保留所有采样时刻，无路径/全部过滤保持不可评价 |

## 交换格式与来源

请求清单版本为`meta3d-lauraycs-request/1`；结果版本为`meta3d-cluster-trajectory/1`。这是Meta-3D整理的交换文件，不宣称是Lauraycs原生导出格式。

- `source`保留taskId、mpdbPath、contentVersion、softwareVersion、additionalLoss。版本未知显式null；原接口不接收附加损耗选择，非null选择拒绝。
- `carrierHz`、`txAnt`、`rxAnt`、`angleCoordinateSystem`、`sourceMetadata`按清单保留，但标明是清单声明，不升级为服务回读证据。
- `timing.source`和`timing.timesSeconds`必须明确、非负、严格递增；与samples一一对应。请求清单只保证所列样本完整，不声称覆盖整个Lauraycs任务。
- `frames`保留每帧身份、时刻、状态与完整聚簇结果；`responses`另存未经字段裁剪的服务响应。算法输出缺多普勒时，仅在规范化副本中补null。
- `collectionStatus=complete`仅表示清单中所有请求成功得到可识别状态；含失败帧则incomplete，CLI退出2。二者均`hardwareEligible=false`。
- `clusterIdentity=frame-local-only`，不把帧内编号当跨帧物理身份。
- 单位固定：s、ns、deg、Hz及复数实部/虚部。空帧、全过滤和执行失败分别表示。

接口不返回源文件内容版本，也不保证多次请求期间文件不变；清单中的版本字段不能证明服务器读取一致性。因此本片保持离线研究用途，不启用正式执行。
源H可能已包含天线与极化响应：MiRT的WANT_H分支优先取channel.H，否则调用包含收发Jones向量的channelCoefficients。不得直接再乘一遍天线模型。

## 实现清单

Meta-3D：
- `scripts/s5_evaluation/lauraycs_collect.py`：原接口采集、请求前校验、逐帧失败留存、原始响应留存、HTTPS与明确授权头、禁止重定向。
- `scripts/s5_evaluation/cluster_import.py`：命令行包装，直接调用CE公共模块；不保留校验或计算副本。
- 对应测试、README及原roadmap同源状态。

ChannelEgine：
- `mimo_ota_simulator/imported_cluster_trajectory.py`：严格读取、结构校验、逐帧模型频响；不修改既有聚簇、合成与ASC输出路径。
- 对应测试及模块使用文档。

原始MPDB、Lauraycs、仪器驱动与正式多快照拒绝门均不改。不新增SCPI，本片仪器手册查询不适用。

## 验证与完成边界

先红测试再实现：真实HTTP封套、错误身份、请求失败、超预算、无路径、全过滤、非均匀时间、复H、未知值、CE真实函数消费。同一条本地HTTP测试链只替换外部Lauraycs服务，必须明确标记合成，不冒充38帧原样本原生计算。
关键逆变异覆盖偷换时间、丢虚部、错身份被接受或失败帧消失。独立内审后推送各自GitHub分支，显式触发外审。

本片交付的是既有接口采集和CE直接接收，不是完整S5c关闭。完整非均匀OTA轨迹合成、源H/天线/极化与坐标适配、正式资产执行及设备验收仍须另有真实证据。
