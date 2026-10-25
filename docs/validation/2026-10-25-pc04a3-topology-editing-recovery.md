# PC04A3 拓扑编辑恢复阶段验证（WIP）

输入基准 `5812f08987cd52a57fc065a2e4cb7114f473162c`。2026-10-25按用户15分钟时限推进Task2，截止13:58:52Z前暂停；本记录不表示PC04A3完成、可合并或现场验收。

当前最小实现：显式引用边改接/删除及中间节点删除先原子拒绝；删除探头自身不被自身声明拦截；数值损耗可编辑。前端错误在事件层捕获并保留抽屉、输入与草稿。POST/PATCH合并/模板替换共用保存校验，复用既有解析器只解释声明子图，不限制无声明旧图读取、不判断硬件/绑定资格。取消显式声明有专门确认，图内给出人工替代路径流程。

实际验证：后端同根8文件165 passed（839 warnings，96.78s）；前端相关4文件39 passed；恢复变异后新后端17 passed；production build成功（最后12.02s，有分包警告）。前端引用保护变异3项红，后端跳过保存保护变异2项红，均已恢复。基线RED的损耗表征测试曾有dataclass/矩阵访问写法错误，已修正，不计入功能RED。

可重跑命令（各后端轮次必须独立mktemp并显式三项环境，mktemp失败阻断）：

```bash
# cwd api-service
task_db_dir=$(mktemp -d /tmp/pc04a3-green-XXXXXX) && test -d "$task_db_dir" && DATABASE_URL="sqlite:///$task_db_dir/green.sqlite" USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true .venv/bin/python -m pytest tests/test_pc04a3_topology_recovery.py tests/test_pc04a1_topology_editing.py tests/test_p1_57_topology_lab_context.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_gui_contract.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_freeze.py tests/test_pc06a1_batch_plan.py -q
# cwd gui
npx --yes tsx --test test/topologyDraft.test.ts test/pc04a2RouteCalibration.test.ts test/topologyOperationalLabContext.test.ts src/features/TopologyEditor/baseStationPortsTruth.test.ts
npm run build
```

真实浏览器新库由默认bootstrap创建，6 seeders/+116/0failed，所有category mock；使用18081/5188，不触碰已有8000/5187。数据库 `/tmp/pc04a3-Fskn5V/browser.sqlite` 保留，现场边界为全HAL Mock。默认启动/HAL日志、运行日志、输入hash和截图位于本机 `output/playwright/pc04a3/`；必要团队验收须补共享证据，不能依赖该本机路径作最终验收。

真实插线定点最终通过：引用边改pin/删除会拒绝并保留输入；新增A/B线缆→真实鼠标拖两边→探头重声明完整路径→删除旧边→真实PATCH/GET→reload，线缆两邻边损耗和2dB（不是4dB），新边无旧校准值。新chain由服务器选路API返回。该定点脚本第七次运行exit0；前六次动画/严格定位/原生confirm/拖线操作问题均留痕，不算通过。

未完成：19类完整逐类浏览器矩阵、端口改名替代流程、取消声明确认完整正反例、旧脚本新库重跑、离线重试/跨lab/采集pending全编辑冻结、最终全后端、独立累计内审和PR外审。父计划及roadmap保持未完成；无正式测量/采用/认证结论。详细本地交接在 `.superpowers/sdd/2026-10-25-pc04a3-topology-editing-recovery/task-2-report.md`（不随仓库共享）。
