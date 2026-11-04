# PC-05A 多频实测点适用范围

承接已批准总设计 §5.3 与连续开发授权，WIP=1。单频片已由 PR #554 合并为 `f51a542d`；本片不关闭 PC-05 父项或现场 B。

## 故障与范围

多频查询原来仅检查扫频起止范围后调用 `np.interp`，将未实测中间点作为补偿返回，API 对实测点也恒标 `interpolated=true`。模型没有经验证的插值域/误差证据，因此收窄为实际样本，不新增推定容差。

验收关系：GET 多频路损 → 当前链身份、来源、有效期与精确采样点 → JSON补偿值；缺点404，实测点200且interpolated=false。查询所有有效候选按时间倒序，新记录缺点时允许读取旧有效实测点。数组不对齐、重复目标点、非数或非有限样本不得供值。历史行、扫频采集与其仪器调用均不修改。

`git grep` 生产调用全集：该getter只有 `api/path_loss_calibration.py` 调用；编排器仅构造多频service，未发现该实例的方法调用；另一个API调用采集，不消费本getter；GUI无直接调用。单频readiness/freeze与历史报告不走本入口，不借本片改动。服务、API、模型说明为修；对应测试与本文/roadmap为验证及状态记录。

memory已核对当前流程；目标文件禁令已搜索。NotebookLM不适用：没有SCPI或仪器语义变化。验证档位为影响面明确的局部修复；字段/类型/路由不变，不改共享契约，相关回归和真实HTTP序列化覆盖唯一消费者。接口四镜像中YAML/生成TS保持boolean契约，不需要重新生成；另跑production build确认消费兼容。不以旧全量冒充本片结果。

## 验证

基线 `f51a542d`；Python3.13.7/pytest9.0.1，复用主目录现有虚拟环境与node_modules。所有测试在api-service，以 `DATABASE_URL=sqlite:////tmp/pc05multi-*.db USE_MOCK_INSTRUMENTS=true PYTHONPATH=.` 显式隔离；不连接仪器或运行库。

- RED：`.venv/bin/python -m pytest tests/test_p2_32a_multi_frequency_activation.py -k formal_sample -q --color=no`，5 failed / 13 deselected / 52 warnings / 0.17s；五例分别证明实测标记错误及两个未测点被插值。日志 `/tmp/pc05multi-red.log`。shell尾随tail的退出码不代表pytest退出码，以日志失败统计为准。
- GREEN相关：`.venv/bin/python -m pytest tests/test_p2_32a_multi_frequency_activation.py tests/test_p1_53_multi_chamber_calibration_isolation.py -q --color=no`，44 passed / 151 warnings / 2.64s；含三实测点、两中间点、真实HTTP、近记录遮蔽、精确新记录优先和换线拒绝。日志 `/tmp/pc05multi-final.log`。
- 未运行本片后端全量，理由见验证档位；不宣称全仓绿。模型docstring明确插值系数不是适用证据，字段仍保留兼容历史。

后续仍包括共同适用投影、撤销及历史处理等PC-05剩余范围；宽带占用范围、插值误差与不确定度不能由此样本点查询证明。

- GUI目录 `npm run build`：exit0，Vite built in 21.26s；既有大chunk警告保留，日志 `/tmp/pc05multi-build.log`。

内审F1发现JSON列可能含非数组，原长度/索引判断会500并遮住旧有效点。已在索引前收窄为list，补对象/标量三种记录回退断言；相同相关命令用 `/tmp/pc05multi-internal.db` 重跑，exit0，44 passed / 154 warnings / 2.55s，日志 `/tmp/pc05multi-internal.log`。这是实际改动后的必要重跑，不复用旧结果。

F1守卫逆变异：删除两行list限定，formal_sample子集exit1，1 failed / 4 passed / 13 deselected / 66 warnings / 0.19s；finally双向assert恢复原文，日志 `/tmp/pc05multi-mutation.log`。恢复后代码与44项通过版本一致。
