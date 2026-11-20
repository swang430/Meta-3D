# 实际材料类型修复：独立内审 CLEAN

轻量定点复审。范围为当前远端基准c42b8c1f后的5处比较收窄及1个测试方法；不涉及同时在工作树内的其他文档改动。未修改源码、未调用硬件或外部服务。

## 功能结论

原有Python嵌套对象相等会把JSON的true与1、7.0与7视为相同，使源材料类型不符仍被签为一致。本次将三份实际材料内容和独立关联pairs统一换成既有frames_sha256规范JSON指纹比较，并对源frame_index要求type(...) is int，拒绝bool。未新增证据机制，修法属于收窄过宽条件/换比较来源。

完整同根比较点已核：

- raw_paths.paths、final_membership.clusters、cluster_export.model均使用同一严格内容比较，覆盖向量分量、功率、延迟、簇编号及公共字段等嵌套值；不是只挡BSID一处。
- association.links.pairs对完整两端关联对象作严格内容比较，持续ID、局部ID及成员均在比较范围。
- raw_paths.frame_index先严格int再核对wrapper索引；wrapper此前已严格int及连续性校验。
- 其余来源比较为必须等于已验证字符串的批次、方向、路径、时间、帧ID及SHA256，不存在bool/int相等入口。mapping的持续ID/局部ID/槽位仍在正式输出前经_integer严格int；member_ids与实际同帧成员比较的另一端已由单帧函数限定为字符串。跨帧载频、坐标相等是已经过数值合法性检查的物理量比较，不应机械改为JSON类型一致。

真实和合成均在单帧数值分支之前经过以上来源及关联核验。CLI和直接函数入口共用，清单与CSV消费仍在全部验证之后。缺失、未知、类型不符均拒绝；没有兜底补值或新放行路径。

## 证据

复用已读取的作者结果：

- /tmp/gcm-trajectory-content-types-red.log：21项中的3个子场景失败，表明原逻辑确实放行export_bool/source_index_bool/association_bool。
- /tmp/gcm-trajectory-content-types-green.log：Ran 34 tests / OK，覆盖已合并单帧及轨迹集成，不再依赖其他工作树PYTHONPATH。
- /tmp/gcm-trajectory-content-types-mutations.log：4项变异被检出。content_types恢复5处原逻辑时3个子场景再次失败；文件字节、关联对应和时间碰撞核心保护仍能检出，无需重复同输入全量或重复造变异。

独立补查同根非同字面值站点：
`python3 /tmp/gcm-trajectory-content-types-review-probe.py`
退出0，详见/tmp/gcm-trajectory-content-types-review-probe.log。分别篡改实际raw_paths向量0为false、final_membership簇ID整数为同值浮点、association局部簇ID为同值浮点，重算实际文件及关联哈希后均拒绝，确认三类完整实际消费点真的收窄。

## 本轮输入指纹

- 基准HEAD：c42b8c1f5acee73e5f202c307e71f20ce8e98d2e，以上修复当前未提交。
- scripts/gcm_trajectory.py SHA256：a5355707435927ec554ec1ec1526c328f66425e5b884f0e7891311ea2502330f
- scripts/tests/test_gcm_trajectory.py SHA256：0d05eb6e45f45bc155e21eb1aed02ee4f60a43d87d23c420e2c08fee5c8705a0

无新功能发现或测试建议。此结论只覆盖本轮内审内容；应由后续GitHub外审核最新修复HEAD，不能以当前旧HEAD的R1结果替代。生产后端与GUI未受影响，既定验证分档不变。
