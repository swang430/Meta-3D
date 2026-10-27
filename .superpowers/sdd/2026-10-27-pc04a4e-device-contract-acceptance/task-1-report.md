# PC04A4e Task1 实施报告

## 范围与判定

输入基线 `bd71f2d8919f24d2091f07ba8e3670ff8687aca5`。仅新增 `api-service/tests/test_pc04a4e_device_contract_acceptance.py` 与本报告；未改生产、共享fixture、资格、历史模板或既有验证结论，未push。独立规格/质量审查由root另行安排，本报告只有实施者自查，不冒充独立审查。主claim继续由root管理。

使用 work-ledger、executing-plans、verification-before-completion。已resolve并读PROJECT/handoff、任务brief、progress、plan-review增量及计划Global Constraints/§0/§4/§5、AGENTS/CLAUDE；memory精确关键词查询无命中，不据旧记忆作结论。无新增仪器语义、命令或驱动改动，NotebookLM不适用。生产关系关键词查得182处，本片只新增组合验收，不借枚举扩修。

## 新增/复用覆盖

| ID | 本片真实执行组合 | 复用但重新跑的原覆盖 | 身份与证据 |
|---|---|---|---|
| E01 | 标称metadata/角色/pair/owner同图POST→PATCH→GET；SQL验证opaque、稀疏缺键；非法pair422原子；原caict_v4真实import→只读preview→CAS确认局部SA转换 | 4a final_graph/nominal_properties、4d conversion的POST/PATCH/import、默认位与CAS反例 | `cases/test_e01_combined_post_patch_get_and_real_template_conversion.json`：请求响应、Lab/暗室/新图/导入图、SQL前后与模板hash；模板原件完全不变 |
| E02 | 正常/参考模式交叉引用，remove/rename port、错pair、删边、BSE dl方向冲突×普通PATCH/conversion共10例；合法整体重接后删旧口，缺方向/unknown不变双向且生产parser拒绝贯通 | 4b port_contract/identity、4c internal_contract/routes/identity；conversion没有删边能力，伪造delete字段422，不称支持删除 | 10份`test_e02_cross_mode_references_atomic[...]`真实422及SQL前后；合法重接例记录HTTP；未把未知方向解释成自动能力 |
| E03 | cable正常模式与receive_cable参考模式各两边2/2：通用4→owner2→撤销4，calibrated0不fallback、null未知、跨模式半组原子拒绝，相位30不变；接收线作为正常正式binding明确拒绝 | 4d loss_truth的未选owner、上游组不加末边、独立撤销与有效量值源；原compensation消费者 | 两份`test_e03_http_group_undo_zero_unknown_and_terminal[...]`。仅正常cable正式末边为2/0/None；参考receive_cable不授正常执行资格，不拿它假作正式binding正例 |
| E04 | 真生产采集/preview/confirm后首执行冻结；HTTP元数据与owner分步保存；同run再次preview/confirm，新执行冻结仍28；ChannelEngine实际补偿入口消费28、probe_gain=0；pin/pair改接拒旧匹配 | 原application/freeze/compensation的其余匹配、混合来源、缺测与报告消费反例 | 合并E04/E05证据含run、两个application、两个execution及SQL/封套/冻结，旧证书/首采用记录/run/首freeze不变 |
| E05 | 实际selection顶层非空参考边含`pa-reference-edge`；该边数值键缺省，仅改`pa_gain_db`metadata，SQL仍缺键；正常connections不变、参考metadata回显且route_digest不变；同run重预览重确认及新freeze | 4a nominal_identity保形与4d正常/参考归属组合；不以其旧结果替代本片正例 | 正常链`conn_p0v`→`probe_0_v`；原参考图`probe1v`显式映射到`probe_0_v`，PA边不是正常末边。GET run取`result.configuration.route_selection`，DiagnosticRun取`sequence_evidence.extra.fixed_route_acquisition.configuration.route_selection`，采用才取`selection_snapshot` |
| E06 | 已解析正常链＋SQL制造历史缺ports/internal_paths参考receive_cable，HTTP owner转换保存，scope/compare200且需review；selected-route与acquisition422，DiagnosticRun/application/selection均零新增；无calibration模式不投影参考owner | 4d loss_truth全参数化盘点与严格采集边界、batch API/safety | `cases/test_e06_legacy_reference_scope_not_capture_permission.json`及专属`application.db`；缺声明原行是隔离历史fixture，不赋予新图或采集资格 |

## E04/E05完整对象身份

最终相关集证据目录 `/tmp/pc04a4e-quy1R7`：

- Lab `0af4beda-9e1c-4f74-91fa-7d2def516b30`，暗室 `5ebccec6-4018-4497-9a28-297ffb452172`，拓扑 `164d384d-75a5-4c4c-9535-8360a0f2b5ea`。
- chain `conn_p0v`，probe `probe_0_v`，正常cable `wire`/边`owner`，参考PA边`pa-reference-edge`，参考器件`reference1`、`rx-cable1`、`sa1`。
- run `b985c04e-f076-431c-afcb-0d5bb57b40b7`；首application `f5d2a901-bc7a-4f11-840c-8f89be0891fc`；重确认application `46373ccd-bf2c-4000-9a10-fb26a1268517`。
- 首execution `2841f37a-0015-4a4d-84b1-464156bcffbd`；二次execution `ca507676-95fe-44b6-a760-0697ae7d94a5`。
- 主库 `related.sqlite`；本case实际API/采用/冻结隔离库 `pytest/test_e04_e05_selected_referenc0/application.db`。所有请求/响应及所取封套、SQL、旧新freeze均在同名case JSON。

E01另有Lab `1fb8ce67-15d8-4e9d-b5fd-5fe45bc2827c`、暗室`8260461d-2864-4b18-9152-4329e4a36e62`、组合新图`fae506c8-ac20-4d1a-a486-bb4c31719663`、真实import原图`460c14f5-11f2-44b4-884e-10a38ad38d20`。转换只声明`fsva3000`/邻接`sgh`端口闭包，其余节点、全部边与模式保形，不改模板。

## 运行与失败收敛

每轮在app导入前通过shell指定全新`/tmp/pc04a4e-XXXXXX/related.sqlite`与两个true开关。最终launcher在导入前检查DB文件不存在与URL/开关，默认bootstrap后显式逐category设置Mock并核验；默认bootstrap没有Lab，`bootstrap-mock.json`记录7类全Mock和空Lab集。新增采集case另验证其专属Lab绑定/类别初始全Mock。`real_capture`只在该case专属库将绑定设为real语义，真实生产驱动类的外部VISA使用既有`_ScriptedVisaResource`、192.0.2.10；不是实物证据，不可宣称所有旧测试绑定始终Mock。

所有首轮与后续失败均保留，没有产品RED，不回退生产造RED；未做生产变异。按失败形状定位修本片测试，不把重新择绿作为故障修复：

| 目录 | 实际统计/退出 | 失败归因与修订 |
|---|---|---|
| `/tmp/pc04a4e-FiwV7O/task1-initial.log` | 14 failed / 2 passed / 189 warnings / 16.61s，pytest exit1 | 新验收脚本把gain元数据放cable、模式缺name、receive_cable放正常显式链；修输入，不是产品RED |
| `/tmp/pc04a4e-0dfqtJ/task1-revised.log` | 3 failed / 13 passed / 192 warnings / 16.80s，exit1 | amplifier不能作同线缆owner；receive正常binding正确拒绝；新参考图缺显式ce端口。改回cable、metadata移probe；参考接收线只验通用和正式拒绝；声明端口 |
| `/tmp/pc04a4e-7LCL1K/task1-revised2.log` | 1 failed / 15 passed / 195 warnings / 16.44s，exit1 | 原caict_v4实际是整机而非ce_port，脚本错误StopIteration；按模板现有SA选局部转换 |
| `/tmp/pc04a4e-O6AQUb/task1-complete.log` | 1 failed / 15 passed / 195 warnings / 16.46s，exit1 | 转换SA缺ports，脚本补模板实际使用pin，不猜仪器能力 |
| `/tmp/pc04a4e-AZKszL/task1-complete.log` | 1 failed / 15 passed / 195 warnings / 16.47s，exit1 | SA端口转换触及邻接sgh，补同一局部端口闭包 |
| `/tmp/pc04a4e-ktoLEv/task1-complete.log` | 16 passed / 195 warnings / 16.43s，exit0 | 局部SA+sgh声明已通过；临时考虑的量值转换未作为最终输入，恢复此通过版本后跑最终集 |

早期轮仅shell设置隔离环境并由复用bootstrap fixture建库/核Mock；最终轮增加前导入路径存在性和输入清单核验，不把早期轮冒称有完整launcher manifest。早期未指定basetemp的pytest临时库仍按pytest原路径保留，最终相关集全部归入上述专用目录。

## 最终相关集原件和命令

执行目录 `api-service`，原命令：

```sh
export DATABASE_URL=sqlite:////tmp/pc04a4e-quy1R7/related.sqlite USE_MOCK_INSTRUMENTS=true BOOTSTRAP_ON_STARTUP=true LOG_DIR=/tmp/pc04a4e-quy1R7/logs PC04A4E_EVIDENCE_DIR=/tmp/pc04a4e-quy1R7/cases
.venv/bin/python /tmp/pc04a4e-quy1R7/run_related.py > /tmp/pc04a4e-quy1R7/launcher.log 2>&1
```

launcher实际启动以下命令，Python绝对解释器及UTC起止/退出码见`execution.json`：

```sh
.venv/bin/python -m pytest tests/test_pc04a4e_device_contract_acceptance.py tests/test_pc04a4d_conversion.py tests/test_pc04a4d_loss_truth.py tests/test_pc04a4c_internal_contract.py tests/test_pc04a4c_internal_routes.py tests/test_pc04a4c_internal_identity.py tests/test_pc04a4b_port_contract.py tests/test_pc04a4b_port_identity.py tests/test_pc04a4a_nominal_properties.py tests/test_pc04a4a_nominal_identity.py tests/test_pc04a4a_final_graph_validation.py tests/test_pc04a2_route_selection.py tests/test_pc04a2_route_application.py tests/test_pc04a2_route_freeze.py tests/test_pc04a2_route_compensation.py tests/test_pc04a2_route_eligibility.py tests/test_pc_04a_fixed_route_api.py tests/test_pc06a1_batch_api.py tests/test_pc06a1_batch_safety.py --basetemp /tmp/pc04a4e-quy1R7/pytest -q
```

最终统计：**669 passed，3598 warnings，466.18s (0:07:46)，pytest exit0，launcher exit0**。UTC起止`2026-10-27T05:05:15.928718+00:00`→`2026-10-27T05:13:06.293084+00:00`，起止HEAD均为上述基线，全部输入哈希逐文件重验一致。本片新增16例均通过；其余653例为本轮重新执行的既有相关覆盖，不是只引用旧结果。`related.log`为完整stdout/stderr，`launcher.log`含bootstrap及结束记录；16份`cases/*.json`保存本片真实HTTP请求/响应与显式SQL快照。`input-sha256.json`冻结全部跟踪文件及新增测试输入，launcher结束逐文件重验不变。依赖记录`dependencies-importlib.txt`（venv无pip，`pip freeze`失败/空输出保留，不把空文件作依赖清单）。

最终目录146份原件（含case JSON、日志和各专属DB）的逐文件SHA索引为`/tmp/pc04a4e-quy1R7/artifact-sha256.txt`，索引本身SHA256=`302e528b4916dd0ade40ee202dddab31f6a2fcbebcd2d5b3633c8787a6f2e4a0`；`related.log`=`4ffb7abf758aad68a2b31a9c70b06bc154ec45f914a3b4d186cac2dc3d2aec7a`；`execution.json`=`bbd79e25c5aee1763bde119d5f786582082e1ca6a2add35539ec427d8a8ec38d`。索引不含索引自身，所有早期失败目录继续保留。

已冻结SHA256：新增测试`275a0ec36a6595e2e9d0667ece77341c38b8928bd805d9e92c21134c4b475da4`；模板`9532474f6106b452349a9b84ea1509d6f00702c6e9036b04969e132d965fce91`；launcher`ebfdb4db1b7e9c3f5f53e1c12fa7b48c7dbb28a5d0572a25ca954a8afec600a7`；输入manifest`1599dae6f8b9aa26f09100b8957c66dd055caf79f75523e79aeb6dcc53d09b8a`；Mock核验`e0aad8cfd001d38f3ea23120332b284e0531e0ddb5406c3f64e92701af28ce82`；依赖`b22f9ea3081a08af8c77eadb5e17e1205c8deb562cfdb688ee775fb1b30d5d30`。

## 未验边界与交接

Task1不跑全后端、不启动浏览器/用户服务、不push、不释放主claim。没有共享生产/契约/fixture变化，最终全量判定和责任仍在Task3。未验实际RF导通、实物端口、计量、停发、ASC加载/CE服务、PostgreSQL事务/CAS、现场B/HOLD；脚本化VISA与Mock结果不能解除这些边界。launch按原fixture跳过其它仪器冻结与后台硬件相位，设置completed只是为了检查已有route freeze，不是完整正式硬件测试已运行。尚需root安排独立规格/质量审查，再进入Task2真实浏览器同构图与生命周期。
