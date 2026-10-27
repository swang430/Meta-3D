# PC04A5a 拓扑库软件验收记录

Task3 实施、自查、真实浏览器矩阵、GUI build和唯一后端全量执行完成，等待独立审查。全量为 **3 failed、8003 passed、17 skipped**，不是全绿；失败及归属如下，不代表现场验收通过。未push。

## 版本与隔离

- 功能版本：`8eb1fb10773f27fabcf6b6684da47b1a5f900140`；测试输入冻结提交：`7d624cd4c82d273d43a00be687cb77b5fa6553ae`，只同步3个获准replace测试分支并新增只读audit，没有改生产源码。其后仅证据/本文更新，不使功能输入漂移。
- 新库：`/tmp/pc04a5a-s1qHHo/browser.sqlite`，先设置 DATABASE_URL、USE_MOCK_INSTRUMENTS=true、BOOTSTRAP_ON_STARTUP=true、专用LOG_DIR，再导入app/bootstrap。提交后及浏览器验收后只读核验8类别、21绑定均mock。
- 专用API18105、Vite15105；启动前端口空闲，未停止其他进程。没有访问或改动原CAICT、默认库或用户服务。
- Task1首次实现前RED原件复用，不追认：`output/playwright/pc04a5a/browser-red.png` 与 `browser-red-api.txt`，真实copy404、多图无库入口。

## 已执行软件链

真实headed浏览器 session `pc04a5a-task3` 使用实际UI鼠标/键盘，真实API保存重读。证据在 `output/playwright/pc04a5a/task3-*`，其中 `.txt` 保留具体操作和断言、`task3-requests-final.txt`保留请求序列。没有React handler代点击、没有伪造成功响应。

- 101图全集实际出现 `skip=100&limit=100` 第二请求，并选到最旧原图；改名name-only、复制201、重读inactive/nondefault、设浏览器默认、重载恢复与选回原图。
- 原图raw三JSON列与同seed未编辑姊妹图完全相同，2020时间戳保持；副本仅两个已有calibrated字段置null，字符串数字/缺键/opaque保留。只读命令：`api-service/.venv/bin/python api-service/tests/pc04a5a_browser_audit.py /tmp/pc04a5a-s1qHHo/browser.sqlite`，exit0；结果 `task3-db-audit.json`。
- 真实RF resolver重读仍为原活跃001：`1cbb90d9-e847-476f-ada9-37d4eb5b56e7`，不是浏览器默认副本。响应 `task3-formal-resolver.json`。
- 共享暗室不同Lab及跨category偏好独立；失效UUID提示回退；localStorage读/写异常明确提示；GET失败不清偏好、不自动导入；模板查询失败与重试。
- 专用空库显式首次模板导入，`replace_existing=false`，图inactive/nondefault，UI库“非活跃”及画布“草稿”，未产生正式执行选择。
- dirty切Lab/category/图/复制受阻、断网保存失败保留草稿；真实拖动原CE保存PATCH200；保存/转换在途锁；复制双击只一条POST；写超时提示核查且不自动重试；迟到GET不覆盖新Lab；离页返回重入不串图。
- Mock采集分两次：真实POST成功但故意丢回应/阻断恢复GET的开始未知，以及真实POST202已拿活动run后终态GET断网；两种UI都保持库/复制锁，开始未知时切Lab也阻断；恢复GET后真实run终态释放。没有confirmed/采用，不把Mock读数作为实测。原件 `task3-collection-unknown.*`、`task3-collection-terminal-unknown.*`。

页面加载时序、自动打开器件Modal、未声明端口pad真实422，以及等待合成文案的验收脚本异常均保留，后续按实际UI独立重验；没有为通过而放宽产品门或隐去失败。详见本地 `.superpowers/sdd/2026-10-27-pc04a5a-topology-library/task-3-report.md`。

## 回归与构建实际结果

`gui/npm run build`：exit0，7841 modules，`✓ built in 11.49s`；既有动态/静态混合import及大bundle警告仍在。完整原件 `/tmp/pc04a5a-s1qHHo/gui-build.txt`；提交的 `task3-gui-build.txt`仅清理两行末尾空格。4份失败脚本日志亦仅清理EOF额外空行，原同名副本备份于该/tmp目录，未删诊断内容。

api-service新目录 `/tmp/pc04a5a-bVTtPK`，环境同上，执行：

```bash
.venv/bin/python -m pytest tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_eligibility.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a4d_conversion.py tests/test_pc04a4d_loss_truth.py -q
```

exit1，`3 failed, 186 passed, 1768 warnings in 222.56s (0:03:42)`。完整原件 `/tmp/pc04a5a-bVTtPK/related.txt`，SHA256 `f43cbbea120d5ef6addea6486072e785c76ebdb1764afd855b6630817f69a678`。

3失败均在 `test_pc04a2_route_application.py`：

- `test_topology_with_adoption_history_cannot_be_hard_deleted[replace]` 仍要求409文案含“采用”。
- `test_delete_race_and_unrelated_constraint_are_distinguished[adoption_after_precheck-replace]` 仍要求进入删除预检产生winner。
- 同函数 `[unrelated_dependency-replace]` 仍要求走到FK删除500。

5a已有库模板覆盖先409，故这些旧分支不再进入删除。root核实后批准仅同步replace：409保护、原始图/原采用记录不变、删除预检未进入/winner为空；delete/chamber及delete竞态原断言不动。两函数全参数定点在另一新库 `/tmp/pc04a5a-xwxLtv/test.sqlite` 执行：

```bash
.venv/bin/python -m pytest tests/test_pc04a2_route_application.py::test_topology_with_adoption_history_cannot_be_hard_deleted tests/test_pc04a2_route_application.py::test_delete_race_and_unrelated_constraint_are_distinguished -q -o log_cli=false --color=no
```

exit0，`7 passed, 103 warnings in 18.30s`。原件 `task3-fix-focused.txt`；未再跑第二个相同6模块集，最新输入由后续唯一全量覆盖。

## 唯一最终全量与已知边界

2026-10-27启动、10-28终结；只执行一次。api-service目录、新库 `/tmp/pc04a5a-uGPFZA/full.sqlite`、Mock/bootstrap及专用LOG_DIR在Python导入前设置：

```bash
env DATABASE_URL=sqlite:////tmp/pc04a5a-uGPFZA/full.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a5a-uGPFZA/logs .venv/bin/python -m pytest tests -q
```

exit1，`3 failed, 8003 passed, 17 skipped, 9811 warnings in 812.90s (0:13:32)`，收集8023项。完整原件 `/tmp/pc04a5a-uGPFZA/full.txt` SHA256 `a03fdd335b216fef7be4ed824d85c4f95b93c9e0c698efa5b3a0787d10294195`；`task3-full-summary.txt`只是原件末48行摘录，不冒充完整日志。

| 失败门 | 本轮实际触发源 | 结论边界 |
|---|---|---|
| G8 | `docs/plans/2026-10-25-pc07a1-validation-evidence/task-3-report.md:111` 的具体UUID execute路径 | 既有历史执行记录被门作现状路径；本片未改历史或门 |
| G11 | `.superpowers/sdd/2026-10-27-pc04a4e-device-contract-acceptance/task-2-report.md:128` 的 `/api/v1/ws` | 既有报告被REST路径门命中；没有新增或改变代理/路由 |
| gitignore已跟踪源门 | 7份既有4e SDD报告及5a Task1报告/修复报告，共9文件被 `.superpowers/sdd/.gitignore:1:*` 命中 | 本片没有force-add SDD、不删除历史、不自动改ignore |

以 `git ls-tree 8eb1fb10 <触发文件>`、`git diff 8eb1fb10..7d624cd4 -- <门和触发源>`（无差异）及 `git check-ignore --no-index -v <SDD报告>` 核实归属；只声明本轮失败及BASE已存在，未额外在main跑门或全量，不能称main全量已验证。相关资格、确认采用、冻结、转换、损耗真值及本片44例库API测试在本次全量通过。以上3门保留待root独立审查/裁决。

输入manifest `task3-inputs-final.sha256` SHA256 `60f44d74d3e40aa71abd7b852b60f63b5c23c22516e1779a085f8e640e6fa439`，全量运行间/结束后 `shasum -c` 均exit0，结束时tracked diff为空。环境Python3.13.14/pytest9.1.1、Nodev26.5.1/npm11.17.0，依赖不变；GUI相关输入未变，build按输入一致复用，不因测试提交号重跑。后续只补dated验证记录和证据，未改测试输入。

## 明确边界

仅软件/Mock证据，不证明真实硬件、现场导通、实测校准、计量资格、正式客户报告或B/HOLD解除。5b持久修订/历史恢复、5c原CAICT独立PA改接、5d综合验收未实施；旧NULL topology_id证书兼容及现有直接DELETE局限不变。后续输入变化须重判验证，不能把本次3失败包装成全绿。主代理自查不是独立内审；环境和原件保留供root审查。
