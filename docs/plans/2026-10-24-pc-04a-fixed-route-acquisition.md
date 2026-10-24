# PC-04A 固定通路自动采集实施计划

> 执行方式：主代理顺序执行 executing-plans；独立只读功能审查按仓库规则进行。每项先观察失败，再最小实现，不并行开展其它功能。

**目标：** 开关保持不动，按已保存链路自动采集两端功率、计算损耗，支持取消及历史查看。
**架构：** 复用现有HAL控制权、驱动命令、链路解析与DiagnosticRun；新增局部采集服务和类型化接口，不写旧校准证书。
**技术：** Python/FastAPI/SQLAlchemy/Pydantic，React/Mantine/React Query。
**设计：** `docs/design/2026-10-24-pc-04a-fixed-route-acquisition.md`，用户已明确批准自动开发及浏览器Mock验证。

## 共同约束

不切开关、不移动转台、不加载/启动未知仿真；请求设置值不当实测。实际RUNNING状态、零输出损耗、完整单次SA测量与正确单位才可计算。Mock显式模拟且功率/结果为空。配置变化只提醒复核，不改变就绪；不自动补偿，不改变正式来源白名单。参考资料见设计§2，所有新增仪器字面量须邻近精确出处。

## 任务1：类型与真实命令采集

- [ ] 测试 `tests/test_pc_04a_fixed_route_acquisition.py`：参数1输出实测，单次SA完成和DBM单位，28dB损耗/负增益，STOPPED/not-ready/错误/取消/停止拒绝，Mock无真实读数。
- [ ] 运行 `.venv/bin/python -m pytest tests/test_pc_04a_fixed_route_acquisition.py -q`，记录缺少采集契约/方法的RED。
- [ ] 新增 `schemas/fixed_route_acquisition.py`：`FixedRouteRequest`（不接受实测值）、`FixedRouteSample`、`FixedRouteResult`（状态/清理/原始回复/来源/计算/缺项）。
- [ ] 新增 `services/calibration/fixed_route_acquisition.py`：`async collect_fixed_route(ce, sa, request, *, output_port, cancel, result)`，只消费传入的本次冻结请求/仪器。F64命令拼装与Mock共用；FSVA完整功率事务落在 `hal/rs_fsva.py`，不改变旧IQ消费路径。
- [ ] GREEN后提交本任务；所有异常先停止本次单音，再保留失败/部分记录。

核心计算用独立已批准公式，不复制旧gain/abs路径：

```python
assert result.net_loss_db == 28.0  # 源端-20，接收-50，接收线缆2
assert result.formal_eligible is False
assert result.cleanup_confirmed is True
```

## 任务2：配置、后台作业与审计入口

- [ ] 新增 `tests/test_pc_04a_fixed_route_api.py`，真实临时DB/HTTP验证链选择、绑定漂移写前拒绝、开始/查询/取消/历史、跨实验室拒绝、重启中断、连续两次与活动测试互斥；先RED。
- [ ] 新增局部API `api/fixed_route_acquisition.py`，注册到`main.py`，路径统一为 `/lab-profiles/{lab_profile_id}/fixed-route-acquisitions`，POST开始、GET历史、`/{run_id}` GET进度、`/{run_id}/cancel` POST请求停止。
- [ ] 新增 `services/calibration/fixed_route_jobs.py`，在HAL控制权进入前重新核对配置摘要/所选链与F64/SA绑定；与当前执行互斥；强引用同一驱动。本进程仅一个作业，`asyncio.Event`请求取消，保存到DiagnosticRun，后台持独立DB session，不借请求session跨任务。
- [ ] GET只解码历史，不从当前配置补真；没有本进程任务的旧running记录显示interrupted、停止未确认。单进程运行约束检查部署入口；不引入通用调度平台。
- [ ] GREEN并提交；证明旧校准表计数不变。

## 任务3：实验室界面与四镜像

- [ ] 在 `gui/src/features/LabWorkspace/FixedRouteAcquisitionCard.test.tsx` 写选链/只读功率/开始/取消/模拟/切lab清空RED。
- [ ] 新增 `FixedRouteAcquisitionCard.tsx`，接入`LabOverview.tsx`；链与仪器用服务器配置盘点，填充已有资料，只让操作员补参考天线位置和线缆来源等缺项；PC-02人工卡明确更名，不冒充自动采集。
- [ ] `labProfileService.ts`增加类型化调用，`types/api.ts`引用生成类型；同步live OpenAPI、`api/openapi.yaml`、`api.generated.ts`。后端测试核验路由及字段一致。
- [ ] 运行相关GUI测试及production build，GREEN后提交。

## 任务4：完整验证与独立功能审查

- [ ] 定点与同根相关回归，最终后端全量（本片新增安全生命周期/证据契约）；GUI受影响契约/build、compileall、Alembic单head、base到工作区diff-check。
- [ ] 独立内审只读，提供累计范围、增量、实际输出与核心反例；功能P1收口，不因测试强度反复加机制。
- [ ] 浏览器使用独立临时DB、真实FastAPI和Vite、HAL全Mock，无响应拦截：选链→开始→模拟结果→历史→再次开始→取消；确认无实测功率/校准资格和旧证书写入。截图/响应/日志保存在仓库外证据目录，关闭临时服务。
- [ ] 更新设计/roadmap状态与实际验证，不把PC-04B标Done。

## 任务5：外审、合并与清理

- [ ] Ready PR，提交前只审当前增量；确认GitHub HEAD后触发Codex R1，处理本片P1/P2后触发覆盖最新HEAD的R2。
- [ ] 每次先读issue/review/inline/checks，再决定等待；空review不算完成，不重复触发旧HEAD。R2及以后无P1且合并条件满足即SHA约束merge；否则只以功能P1续审。
- [ ] fetch核合并commit、主目录ff-only，保留用户未提交与仪器资料；安全归档工作树、清理分支、台账交接，说明真实现场仍需PC-04B。
