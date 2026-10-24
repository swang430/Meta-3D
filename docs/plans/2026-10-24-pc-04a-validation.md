# PC-04A 软件验证记录

日期：2026-10-24。基线：`a98736fa`。证据目录：本机工作树外的
`/Users/simon/.codex/artifacts/pc04a-real-mock-20261024`。
这是软件及模拟流程验证，不是 PC-04B 现场量值验收。

## 最终定点与界面

| 实跑命令（对应工作目录） | 实际结尾 | 说明 |
|---|---|---|
| api-service：`.venv/bin/python -m pytest -q tests/test_pc_04a_fixed_route_acquisition.py tests/test_pc_04a_fixed_route_api.py tests/test_rule_gates.py --tb=short` | `104 passed in 21.37s` | `input-final.log`，含34项本片用例；严格数值/确认输入6条先RED再GREEN；真实API→独立session→真实lease→真实驱动，仅替外部仪器传输 |
| gui：`node --import /Users/simon/.npm/_npx/fd45a72a545557e9/node_modules/tsx/dist/loader.mjs --test test/*.test.ts` | `tests 182; pass 182; fail 0` | `gui-verified.log`，沿用本机已缓存tsx，无新增依赖 |
| gui：`npm run build` | `built in 11.87s`，退出0 | `build-verified.log`；修正模拟取消显示的类型收窄后重新构建；旧构建失败不算通过 |
| api-service：`.venv/bin/python -m compileall -q app`；`.venv/bin/alembic heads` | 退出0；`c1e3f5a7b9d2 (head)` | 本片没有数据库迁移 |
| 浏览器：`playwright_cli.sh -s=pc04a run-code --filename <工作树>/gui/test/pc04FixedRoute.browser.js` | `passed:7` | `browser-final-strict.log`；真实FastAPI/Vite/临时SQLite，全部HAL Mock，不拦截HTTP或伪造响应 |

浏览器实际检查：从已有链带出端口及极化；没有两端实测功率手填入口；安全确认前不能开始；真实POST及数据库记录均为模拟、功率/损耗为空；再次采集可取消；刷新保留历史；切换实验室清空输入且历史不串用。
最终两次运行编号：`c06b3453-aed0-4fd6-987b-cf95a7c3f131`、`5d9f64bf-8d3c-42b1-9859-0848d6de964e`。
截图：证据目录下 `output/playwright/pc04-mock-acquisition.png`，已实际查看。

## 核心反例与独立审查

独立只读审查首轮发现：停用F64仍可进入控制权、分析仪旧曲线可能被当新功率、清理失败状态可能被释放异常覆盖、进度请求失败移除取消入口。五条相关反例先RED，再最小修复；增量尾审功能P1=0。
同根补充：测量结束复核输出损耗；正常服务退出先请求停发并等待落盘，再关闭HAL；严格拒绝布尔值转功率和数字冒充安全确认。

进程内核心变异不改磁盘文件：去掉F64输出测量参数1，2条失败；把停发确认强行设为真，1条失败。脚本核对注入锚点唯一、pytest退出1且源文件未改；分别见 `mutation-option.log`、`mutation-stop.log`。后续改动仅输入校验/显示/退出路径，不改这两处算法，复用该证明，不重复全量。

## 后端全量与既有日期基线

api-service实跑：`.venv/bin/python -m pytest -q --tb=short --show-capture=no -o log_cli=false`，最终输出：
`1 failed, 7176 passed, 17 skipped in 281.70s (0:04:41)`，退出1。
唯一失败为下面独立在main复现的过期fixture；没有本片新增失败。证据 `backend-final-stable.log`。
本次全量对应R1提交 `052bb900`，包含全部安全修复及严格输入校验。R1后的局部修复及实际复用边界见下节，不把该全量称为R1修复后完整重跑。
此前全量在发现功能缺陷后主动中止，不能当作完整通过；最终回归不复用那些中止输出。

主目录main独立实跑：
`.venv/bin/python -m pytest -q tests/test_p1_64_quiet_zone_evidence_truth.py::test_channel_status_cannot_be_valid_while_quiet_zone_is_unknown --tb=short --show-capture=no -o log_cli=false`
结果 `1 failed in 0.06s`，断言 `expired != valid`；旧fixture在当前日期已过期。证据 `main-date-baseline.log`。不得为使旧测试通过而改变生产有效期策略，也不把该既有失败宣称为本片新增回归。

## R1共享历史契约修复

外审唯一功能P1 `inline4365940061`：采集记录直接保存原始载荷，遗漏共享诊断详情必须的SequenceEvidence字段，打开旧入口会500。新增真实HTTP反例先复现4项必填字段缺失，再将创建/终态写方统一为既有格式，完整采集数据放在 `extra.fixed_route_acquisition`，专用读取仅取同一份数据。共享API、GUI类型及OpenAPI响应形状未改，不增加新历史机制。

实跑api-service：`.venv/bin/python -m pytest -q tests/test_pc_04a_fixed_route_acquisition.py tests/test_pc_04a_fixed_route_api.py tests/test_p2_28_diagnostic_sequence_evidence.py tests/test_rule_gates.py --tb=short --show-capture=no -o log_cli=false`，**107 passed in 23.46s**；含running和终态的共享列表、共享详情与专用读取。`r1-red.log`、`r1-green.log`保留实际输出。独立增量内审功能P1=0。

本轮仅修改局部保存/读取封套与真实耗时，不改驱动命令、功率计算、安全清理、共享schema或正式执行策略；执行相关契约回归和增量浏览器验证，不为一次推送重复整套后端。全量证据仅复用未改影响面，不冒充相同完整输入。

修复后用新独立临时DB `test-r1.db` 重跑同一真实浏览器脚本，**8项通过**，新增从“调试序列 + 单阶段”最近运行中实际点击“查看完整证据”，真实GET返回200，完整载荷可显示且模拟不是正式成功。`browser-r1.log`，运行编号 `9aeabc85-c153-4460-92b1-42b9a4bdc6c8` / `0eb04185-c7d2-4c9f-af2b-0a0bc90b0e60`；新增截图 `output/playwright/pc04-shared-diagnostic-evidence.png` 已查看。compileall及唯一Alembic head再次通过，GUI生产代码未改，复用已通过的182项/build。

## 尚未完成的现场工作

PC-04B仍须真实F64/FSVA/固定接线/参考天线及线缆资料验证。软件不签发校准资格、不自动写补偿、不切换射频开关；没有资料时保留缺项，不编不确定度。强制结束进程后的停发状态仍需现场确认，正常退出测试不能证明强杀安全。
