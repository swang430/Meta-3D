# 射频拓扑校准整合实施计划

> 主代理使用 executing-plans 顺序执行；独立只读审查按仓库规则调用。用户已批准上轮最终体验及撤除独立表单，沿用PC-04A修订，不启动无关feature。

**目标：** 在现有射频拓扑完成图选通路、自动测量、结果和历史查看，撤掉总览校准表单。
**架构：** 已保存拓扑+服务器解析链形成只读测量图，复用既有采集API及取消生命周期；图中新增的空气/参考天线/分析仪不写入开关配置。
**技术：** React/Mantine/ReactFlow/React Query，沿用现有FastAPI与DiagnosticRun。
**设计：** `docs/design/2026-10-24-topology-calibration-workspace.md`。

## 全局约束

单WIP，不猜端口/SCPI，不切开关，不把模拟或设置值当实测，不计算第二份损耗，不自动改原损耗/正式补偿。历史只读冻结证据，配置变化仅提醒复核。主目录用户规则及仪器资料保留。

## 1. 图的产生和结果显示

- [ ] `gui/test/topologyCalibration.test.ts`先写行为RED：图中的通路身份由服务器解析，不凭名称拼；选B1.1不能连到B1.2；空气/参考天线/接收线缆/分析仪完整；模拟、身份错、摘要变化不假绿；负增益符号保留。
- [ ] 新增 `TopologyEditor/calibrationGraph.ts`，输入 `SwitchTopology`、`CalibrationScopeSnapshot`及所选chain_id，输出图节点/连接及明确的不可测原因；不修改输入对象，不向拓扑保存新增节点。
- [ ] 从既有`fixedRouteDisplay`消费显示结果，不另算损耗。运行 `node --import <已缓存tsx loader> --test test/topologyCalibration.test.ts`观察RED→GREEN，提交。

## 2. 图内采集、历史和辅助操作

- [ ] 重构既有`FixedRouteAcquisitionCard`为无链下拉框的侧栏；选择由图上按钮传入；运行、断网、取消守卫与历史保持同一控制器。
- [ ] 新增`TopologyCalibrationWorkspace.tsx`，图和侧栏响应式布局；ReactFlow节点包含可键盘操作的通路按钮；选择历史在图上只展示身份匹配的冻结记录。
- [ ] `TopologyEditor.tsx`接入“通路校准/连接编辑”，未保存草稿不进入测量，运行中阻止切换和重导入；保持原连接编辑与保存方式。
- [ ] `LabOverview`撤四卡；人工卡退出可达UI；配置复核/F64状态移进图内辅助Drawer，配置复核移除链表格。
- [ ] 明确操作员参考记录关联的保存位置，不写任何损耗字段或启用补偿；若API新增字段，先真实HTTP RED、再实现及四镜像同步。模拟/失败不得采用为真实参考。
- [ ] 相关GUI/后端回归、构建，独立内审只审本片功能与同根遗漏。

## 3. 浏览器和交付

- [ ] 真实临时后端/HAL全Mock浏览器：图选两条不同通路、完整空气段、开始/取消、历史、共享证据、切实验室隔离、总览不再有旧卡；窄屏无横向溢出，实际截图检查。
- [ ] 更新roadmap及当前设计，记录实际验证/风险档，Ready PR，核HEAD后Codex R1→R2，最新HEAD无P1才SHA合并；同步main保留用户修改、清理本片工作树与台账。
