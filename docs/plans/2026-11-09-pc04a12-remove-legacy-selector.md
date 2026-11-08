# PC-04A-12：删除旧PA专用定位下拉框

用户已批准按roadmap连续完成非阻塞项；基准PC-04A-14合并 `d3b21500`。本片只处理“含旧PA标称的连线”专用下拉框：无旧边值的图显示空控件，容易被误解为PA或图未加载。以普通器件、连线、当前草稿与保存修订作为操作概念。

## 范围与验收关系

| 站点 | 本片修改 | 保留及断言 |
|---|---|---|
| TopologyEditor工具栏 | 删除专用Select及内联选项/事件；修正关联说明 | 普通画布连线仍调共享openConnection；节点/连线编辑与采集锁不变 |
| 现行器件指南 | 改为选择适用模式、普通画布边编辑 | 原值、转换能力、确认保存及重载说明保留 |
| 四份pc04a4浏览器脚本 | 已删入口改为普通画布点击或器件显示/模式操作；锁断言改读仍存在的入口 | 不删旧值保形、metadata-only、保存/取消/失败/锁断言，不新增另一种旧PA专用入口 |
| 本片浏览器验收 | 隔离真实API、有旧PA与无旧PA两类图 | 下拉框不存在；普通编辑、保存重载、历史恢复可用；未编辑字段及旧值不变 |

初始全集为生产文件1、依赖脚本4、现行指南1，加本片验收脚本/必要夹具与记录。共享openConnection、getDraftModeConnectionIds还有活调用，不能随Select删除。旧设计/验收原件是历史，不改写；API字段、数据库历史、转换和补偿逻辑不删。属于其他模式的边先切换模式，端点显示限制通过普通器件操作；未归属任何模式的边不自动补归属，也不声称因此获得画布入口。不为测试添加产品专用定位入口。

## 流程

- [x] 规格独立核对；先验证旧页面存在控件使本片要求失败。
- [x] 最小删除及现行脚本适配；逆变异证明控件恢复时验收会失败。
- [x] 相关GUI测试与production build；隔离真实API浏览器验收两类图，保存及历史恢复数据对账。
- [ ] 独立累计内审，Ready PR R1/R2覆盖最新HEAD，合并后同步main。

纯GUI修改，不预设新版完整后端回归；若实际触及共享后端，重新按影响判断。所有写入仅新隔离库，不改用户图/绑定/历史，不部署或重启用户服务，不解除B/HOLD。无仪器命令改动，NotebookLM不适用。

## 已核软件验证（2026-11-09）

- GUI目录：`npx --yes tsx --test test/pc04*test.ts test/pc06*test.ts test/calibrationResultView.test.ts`，**52 passed /0 failed /1521.83ms**，`/tmp/pc12-gui-tests.log`；`npm run build`退出0、**22.06s**，`/tmp/pc12-build.log`。保留既有大分块提示。
- `gui/test/pc04a12OrdinaryEditing.browser.js` 通过真实浏览器、真实API在新隔离SQLite `/tmp/pc04a8-0VhSWA/browser.sqlite` 执行。bootstrap使用既有受保护 `tests.pc04a13_browser_fixture`，全部Mock；API18513、GUI15513，仅本轮测试服务。旧测试库含大量上一片证据，最初脚本曾受轮询延迟影响而超时，改用新库后的结果才作验收。
- 两个新图 `38ff5b40-66c2-42cf-9e66-d2ab5de395a5`、`20ea2542-84cb-4538-b63d-757b9b431747`，分别无旧增益键与旧值12。实际鼠标点击普通连线，损耗1.25→1.75，PATCH保存r2、刷新重新选图，再通过历史预览及确认恢复r1内容为新r3。节点、模式、旧增益缺键/12保持，专用控件不存在。原件 `browser-final.json`、`browser-final.log` 在上述目录；`/tmp/pc12-final.png`已人工查看。两图均停用、不作为采集资格。
- 红测试 `/tmp/pc12-browser-red.log` 明确报“旧PA专用下拉框仍存在”。逆变异 `python /tmp/pc12-mutation.py` 将原控件恢复到真实页面，同一行为断言失败；finally逆替换恢复全文，再跑页面断言通过。结尾 **1 mutation killed by rendered UI; restored source identical and browser assertion passed**，`/tmp/pc12-mutation.log`。5份GUI/旧脚本哈希仍匹配 `/tmp/pc12-ui-script-frozen.json`。
- 四份旧浏览器脚本均 `node --check` 通过，改走已有模式与真实画布点击；本轮没有重跑它们的全部历史场景，不将语法检查冒称完整浏览器覆盖。未归属原边继续断言无关保存/重载后原值、缺键、模式不变；需要编辑旧字符串的断言改为独立初始化的可见同形样本。
- `tests/pc04a4a_browser_fixture.py` 仅新增2个独立端点和1条明确calibration边 `legacy-bad-pa-visible-sample`，旧原件及归属不改。新隔离库运行 `/tmp/pc12-verify-visible-seed.py`，日志 `/tmp/pc12-visible-seed-validation.log` 结尾 **PASS: schema GET / metadata-only PATCH 200 / reload / raw string / original edges nodes modes unchanged**；实际HTTP保存与DB原始字符串“12”一致。

后端改动仅测试夹具，未改变生产、契约或依赖；按GUI档验证，不冒称跑了新版全后端。独立累计内审及外审以本片PR回执为准。正式部署和用户数据操作不在本片范围。
