# 持续簇成员变化修正：独立内审 CLEAN

本轮按全套增量审查新增关联契约及所有消费方；未修改工作树源码、测试或材料。审查基于当前未提交增量，相对既有轨迹提交6def6909。用户明确要求独立来源关联机制，本轮新增该机制不属于越界。

## 功能核验

- 已删除跨帧member_sets相等门，未在其他路径保留相同成员/局部编号限制。映射member_ids仍逐帧与实际同帧最终成员表核对，未把成员真实性检查一起删除。
- association_evidence在真实和合成分支选择之前统一读取；实际文件字节SHA256、批次、方向、完整有序帧哈希、三份实际材料哈希及产生方/版本/方法均核对。关联文件路径不得复用identity_evidence自身。
- 全部相邻间隔必须存在且两端帧ID准确。pairs中的持续ID、两端局部簇ID和两端各自成员同时与逐帧输出映射比较，允许两端成员与局部编号变化。缺关联来源时，同名成员不会被当成持续身份依据。
- 输出仍通过同一簇固定槽位校验；关联两端持续簇集合变化拒绝，未开放出生消失的未知厂商槽位语义。CSV持续ID来自映射而非功率、时延、成员名称或输入列表序号。
- 清单新增association_evidence原始路径与文件SHA256引用；原始材料与身份文件引用、完整帧哈希、两套时间和CSV哈希链未丢失。真实及合成均formal_eligible=false，无正式判定或硬件调用消费者。

## 实跑与复用证据

主代理20项测试结果已读并复用：/tmp/gcm-trajectory-green.log，Ran 20 tests / OK。不重复跑同输入整套。先红日志/tmp/gcm-trajectory-association-red.log明确显示缺关联来源负例在旧实现失败，未将测试脚本空转当红。

主代理变异/tmp/gcm-trajectory-mutations.log已读：文件字节哈希、独立关联pairs一致性、毫秒碰撞3项分别导致对应测试失败；本轮核心关联保护已有可核验证据，无需重复造变异或扩建测试。

独立定点实跑：
`PYTHONPATH=/Users/Simon/Tools/MIMO-gcm-frame/scripts python3 /tmp/gcm-trajectory-association-review-probe.py`
退出0，日志/tmp/gcm-trajectory-association-review-probe.log。结果：

- 持续簇下一帧局部簇编号改为42、原逐径ID改为frame1-ray42并增加frame1-ray99成员，合成正例通过。
- 相同构造材料切到真实来源接口分支、完整重新绑定实际文件后输出38行，前3帧持续ID均为[1,2]；formal_eligible=False；清单关联引用与输入完全一致。
- 真实来源接口删除association_evidence即拒绝。

以上真实分支正例为构造接口验证，绝非本批实测轨迹或物理身份已获验证。

## 域全集与对称路径

新增字段生产方为外部关联来源文件；_load_bound读取并验证字节，_verify_associations核语义，再由_convert_trajectory校单帧成员与槽位并输出，main写CSV/清单。所有生产入口共用此链。真实/合成仅后续单帧数值函数选择不同，新关联门无分叉；直接函数调用与CLI也无绕过。没有新增历史读取、API、报告、下载或KPI入口。文档与计划已同步成员可变化、需独立关联、内容一致性不代表物理认证；没有遗留“持续身份必须相同member_ids”承诺。

原两条时间修复仍在：源逐径时间/索引核对、源TIMESTAMP派生核对、局部Decimal精度均保留。未见本次关联修正造成同根回归。

## 当前输入指纹

- scripts/gcm_trajectory.py：7c991108961e71d310bdd2b75550438133f087066beac4b99f8affc3693f122c
- scripts/tests/test_gcm_trajectory.py：48585e830fc3587cfed80529b39d9b151c5717a857dda7d625d174322882be9b
- scripts/gcm_trajectory.md：18ee8525b200373d0395ffa8d21ae438e79bfc8bc0a466963385f3235c354330

没有新增功能发现或测试建议。独立离线脚本未改变生产后端/GUI行为，按既定分档不要求后端全量或GUI构建。单帧先合并、正式依赖版本复验、外审覆盖最新HEAD及合并同步仍由主代理完成；本报告只签当前内容的内审功能结论。
