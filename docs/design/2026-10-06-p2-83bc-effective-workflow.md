# P2-83B/C：生效状态与受控操作

2026-10-06用户同意聊天中的B/C设计，要求继续完成P2-83。A已由PR #505合并（9878c87a）。主代理顺序实施，B合并清理后才启动C；不自动启动P2-84。

## 已批准方案

B分开显示未保存草稿、当前已保存配置、HAL运行快照/最近激活回执、所选LabProfile执行binding。保存失败不说已保存；保存成功但HAL激活被拒绝仍明确已保存。最近操作回执不是永久运行真值；离开编辑器或页面刷新后没有回执即未取得，不猜上次成功。草稿只在原编辑器内，不复制到服务器binding或总览。

C保留保存→分类HAL激活，提供只重试分类激活的操作；LabProfile同步仍独立显式确认，确认目标Lab和已保存配置，服务器锁内核对确认版本，发生漂移受控拒绝。探头/暗室、射频拓扑沿用原保存接口，统一提示所在阶段及未保存状态。不承诺跨HAL/DB单事务，不自动补偿已成功保存、不强制全局reload。

## 权威源与全集

| 事实 | 产生方 | 消费方/验收 |
|---|---|---|
| 草稿差异 | App内EquipmentManager drafts；hasUnsavedInstrumentSyncDraft | 仪器抽屉；修改型号/endpoint/profile后标未保存，不能当binding |
| 已保存全局资源 | GET /instruments/catalog | 抽屉/总览；服务器成功响应才显示，故障/paused/刷新不沿用旧快照为成功 |
| 保存与分类激活阶段 | commitThenActivateCategory及激活端点回执/异常 | 抽屉；保存失败不激活，激活失败不伪称回滚 |
| HAL当前快照 | GET /instruments/hal/readiness显式lab | 总览/抽屉；原服务器status/detail，不客户端判正式资格 |
| BS/CE执行绑定 | readiness的服务器binding projection | 所选Lab面板；lab身份不一致拒绝展示，Mock只诊断 |
| 暗室/拓扑保存 | ProbeManager/TopologyEditor已有mutation | 原子视图；保存结果与未保存状态独立，不自动同步仪器 |
| 确认后的仪器同步 | sync-current端点category→Lab→connection锁及resolver | C确认窗口→服务器版本校验→binding；并发漂移409且binding不修改 |

通用仪器binding没有BS/CE resolver投影时不得猜成“已解析”；显示尚无该类别解析投影。没有指定TestCase的兼容性仍未评估。所有内容是当前状态，不更改历史冻结证据。

## 分片与约束

B以GUI局部档实施，不改后端、契约四镜像、依赖或SCPI；新增展示组件不搬动整个App。C若补同步请求/响应契约，按四镜像和共享契约档验证全部正式消费者及最终后端全量。Memory已检索且以当前代码复核；NotebookLM不适用（复用既有保存/激活/同步，无新增仪器语义）。

按严格TDD从真实App交互及纯阶段执行器写RED；HTTP/WS transport隔离，不写生产库或触碰硬件。GUI构建、受影响契约/规则门、核心变异恢复核对。独立只读内审后Ready PR，Codex R1→R2，最新HEAD无P1且合并条件通过才merge；结果到达即读取，不重复请求。
