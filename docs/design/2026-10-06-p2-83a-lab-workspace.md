# P2-83A：实验室配置统一工作台与只读总览

## 目的与批准范围

用户于2026-10-06确认将P2-83拆为A（统一工作台与只读总览）、B（配置生效状态展示）、C（受控操作编排），先实施A。
当前可观察问题：仪器资源、探头与暗室、射频拓扑入口分散，操作员不能在同一工作单元通盘查看所选实验室配置。
本文是A片设计，不代表已实现；书面设计复核后进入实施计划。

## 方案裁决

- 推荐：一个“实验室配置”主入口、四个内部子视图，复用原编辑器和现有服务器投影。既改善组织方式，又不改变保存语义。
- 仅改菜单名称：不能提供共同总览，无法解决通盘查看问题，不采用。
- 同时自动保存、激活、同步：涉及硬件与数据库失败阶段，超出A片，不采用；保留到C片独立设计。

## 权威来源与边界

| 事实 | 现有权威来源 | A片行为 |
|---|---|---|
| 当前浏览器选择的实验室 | OperationalLabContext；顶部OperationalLabSelector | 复用唯一选择器，不建第二上下文 |
| 暗室归属 | LabProfile.chamber_config_id；fetchActiveChamber显式lab_profile_id | 显示绑定暗室；缺失或错误单独展示 |
| 仪器资源 | 全局品类、connection、分型号preset；EquipmentManager | 原编辑功能保持；明确标注全局资源不是已同步绑定 |
| 实验室仪器绑定与运行快照 | fetchReadiness(lab_profile_id)返回的binding与HAL快照 | 展示服务器status/detail/model/adapter/digest，不客户端重算兼容性 |
| 射频链路 | fetchRFChains(lab_profile_id)及现有TopologyEditor | 显示服务器拓扑名称、链数量和warnings，保留原编辑入口 |

总览不传test_case_id，兼容性未评估不得显示为“可以执行某用例”。HAL available或binding configured不能升级为正式资格或整体就绪。总览是当前配置/快照，不是历史执行冻结证据。

## 页面与导航

左侧三个独立入口收敛为“实验室配置”。内部顺序：总览、仪器资源、探头与暗室、射频拓扑。
默认进入总览；原有内部导航到equipment/probeManager/topologyEditor仍定位对应子视图，逐个保留调用点，不改到错误页面。
复用EquipmentManager、ProbeManager、TopologyEditor，不搬动其硬件操作逻辑，不为组织页面抽离整个App.tsx。
本片不增加跨子视图草稿持久化，也不宣称离开编辑器会保留草稿；维持现有编辑器挂载/卸载语义。不得通过保留隐藏编辑器引入隐式后台请求或隐藏写操作。
LabProfile切换沿用现有dirty guard及in-flight work阻断，不绕过requestLabChange，不因菜单合并自动保存或自动同步。

## 总览的数据流与错误形态

只在总览激活且selectedLabProfileId非空时读取现有GET；请求、query key及响应归属均绑定同一LabProfile。
使用现有readiness查询键与API访问器，不额外请求基站/信道仿真器preview同一事实；射频链路复用fetchRFChains。
不新增定时轮询；提供手动刷新，只读取服务器已有快照和数据库配置，不调用驱动、SCPI、连接测试、HAL reload或写接口。
响应LabProfile身份与选择不一致时拒绝展示为本实验室数据；切换期间不得把上一实验室缓存当作新实验室配置。
未选实验室、加载中、请求失败、未初始化HAL、缺binding、缺暗室、缺拓扑分别展示；请求失败时旧缓存不能维持成功标志。
展示服务器生成时间；不额外定义本片没有证据的过期阈值。Mock/diagnostic/unknown保留原语义和醒目标识。

## 操作边界

仪器资源保存后分类HAL激活保持原逻辑；“同步到LabProfile”仍是显式独立操作，未保存草稿仍不能同步。
探头/暗室的绑定与射频拓扑保存保持原端点和所选实验室参数。
不修改后端schema、数据库、OpenAPI、执行冻结、认证、校准、KPI或正式provenance白名单。NotebookLM不适用：本片没有新增或修改仪器语义。

## 生产关系与验收

| 生产入口 | 权威判据 | 消费方 | 可观察断言 |
|---|---|---|---|
| App左栏及内部跳转 | 统一导航映射 | 工作台四个子视图 | 无重复旧主入口，所有旧跳转仍到正确编辑器 |
| 顶部LabProfile选择 | OperationalLabContext | 总览及原编辑器 | 请求显式同一lab；选择切换不展示旧lab数据 |
| 总览读取 | readiness及rf-chains服务器响应 | 总览卡片 | 错误/缺失/模拟/未评估不显示正式通过 |
| 原仪器保存与同步 | 已有保存/激活编排与sync端点 | EquipmentManager | 进入总览不写入；保存不自动同步 |
| 编辑中的Lab切换 | 现有guard与beginWork | OperationalLabSelector | 未保存/进行中操作阻断仍有效 |

实施先写RED，再最小GREEN；验证真实App左栏与子视图交互，不只验证孤立页面。相关GUI契约、production build、导航/上下文回归、受影响rule gates和diff检查必须通过。
后端不变，不机械重复后端全量；若实现发现必须改变后端共享契约，先停止并重新裁决范围。
独立只读内审后Ready PR；Codex R1处理本片P1/P2，R2无P1且合并条件满足立即收口；后续仅P1阻塞，修复必须覆盖最新HEAD外审。

## 后续子片

P2-83B负责草稿、已保存资源、HAL激活与执行binding四态的完整展示，不把A片总览误记为B已完成。
P2-83C在B闭环后设计受控分步保存/激活/同步，禁止承诺跨HAL/DB单事务。
P2-84仍待P2-83整体闭环，不随A片启动。
